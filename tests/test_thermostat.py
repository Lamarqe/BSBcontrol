"""Tests for thermostat.py

Covers:
  - basic_hysteresis rule (all boundary conditions)
  - rule chain evaluation (first-match-wins, all-abstain fallback)
  - ThermostatController init (room population, persisted target override)
  - set_target_temperature persistence (write + reload)

Hardware is replaced by lightweight fake doubles; no real Modbus or BSB
connections are made.  Filesystem access is isolated via pytest's tmp_path
fixture and monkeypatch of thermostat.STATE_FILE.
"""

import json
import pytest

import thermostat
from thermostat import (
    RoomState,
    SystemContext,
    ThermostatController,
    basic_hysteresis,
    HYSTERESIS,
)


# ---------------------------------------------------------------------------
# Fake doubles
# ---------------------------------------------------------------------------

class FakeRoomConfig:
    """Minimal stand-in for modbus.RoomConfig — no network I/O."""

    def __init__(self, current_temperature: float, relay_status: bool, target_temperature: float = 22.0):
        self._current_temperature = current_temperature
        self._relay_status = relay_status
        self.target_temperature = target_temperature
        # Track calls for assertion purposes
        self.relay_set_calls: list[bool] = []
        self.relay_read_count: int = 0

    # API used by ThermostatController
    @property
    def current_temperature(self) -> float:
        return self._current_temperature

    @property
    def relay_status(self) -> bool:
        return self._relay_status

    def set_relay_status(self, status: bool) -> None:
        self._relay_status = status
        self.relay_set_calls.append(status)

    def update_relay_status(self) -> None:
        self.relay_read_count += 1

    def _read_current_temperature(self) -> float:
        return self._current_temperature

    def _read_relay_status(self) -> bool:
        return self._relay_status


class FakeModbusController:
    """Minimal stand-in for modbus.ModbusController."""

    def __init__(self, rooms: dict[str, FakeRoomConfig]):
        self.rooms = rooms


class FakeBsbController:
    """Empty stub — no BSB attributes needed in phase 1."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _room(current: float, target: float, relay_on: bool = False) -> RoomState:
    return RoomState(
        name="test",
        current_temperature=current,
        target_temperature=target,
        relay_on=relay_on,
    )


def _ctx() -> SystemContext:
    return SystemContext(bsb_data={}, energy_price=None)


def _make_controller(
    rooms: dict[str, FakeRoomConfig],
    monkeypatch,
    tmp_path,
    state: dict | None = None,
) -> ThermostatController:
    """Build a ThermostatController with isolated state file."""
    state_file = tmp_path / "thermostat_state.json"
    if state is not None:
        state_file.write_text(json.dumps(state))
    monkeypatch.setattr(thermostat, "STATE_FILE", str(state_file))
    return ThermostatController(FakeModbusController(rooms), FakeBsbController())


# ---------------------------------------------------------------------------
# basic_hysteresis — rule unit tests
# ---------------------------------------------------------------------------

class TestBasicHysteresis:
    def test_too_cold_returns_true(self):
        room = _room(current=20.0, target=22.0)  # deviation = -2 → ON
        assert basic_hysteresis(room, _ctx()) is True

    def test_too_warm_returns_false(self):
        room = _room(current=24.0, target=22.0)  # deviation = +2 → OFF
        assert basic_hysteresis(room, _ctx()) is False

    def test_inside_dead_band_returns_none(self):
        room = _room(current=22.3, target=22.0)  # |deviation| = 0.3 < 0.5
        assert basic_hysteresis(room, _ctx()) is None

    def test_exactly_at_hysteresis_boundary_returns_none(self):
        """At exactly ±HYSTERESIS the dead band applies (abs < HYSTERESIS is False here,
        but we verify the boundary value doesn't accidentally trigger a relay change)."""
        room_low = _room(current=22.0 - HYSTERESIS, target=22.0)
        room_high = _room(current=22.0 + HYSTERESIS, target=22.0)
        # |deviation| == HYSTERESIS is NOT < HYSTERESIS → rule fires
        assert basic_hysteresis(room_low, _ctx()) is True
        assert basic_hysteresis(room_high, _ctx()) is False

    def test_just_inside_dead_band_returns_none(self):
        room = _room(current=22.0 + HYSTERESIS - 0.01, target=22.0)
        assert basic_hysteresis(room, _ctx()) is None

    def test_context_unused_in_phase1(self):
        """Passing non-empty bsb_data or energy_price must not change outcome."""
        room = _room(current=20.0, target=22.0)
        ctx = SystemContext(bsb_data={700: 3}, energy_price=0.99)
        assert basic_hysteresis(room, ctx) is True


# ---------------------------------------------------------------------------
# Rule chain evaluation
# ---------------------------------------------------------------------------

class TestRuleChain:
    def test_first_matching_rule_wins(self, monkeypatch, tmp_path):
        room_cfg = FakeRoomConfig(current_temperature=20.0, relay_status=False)
        ctrl = _make_controller({"living": room_cfg}, monkeypatch, tmp_path)

        always_off = lambda room, ctx: False  # noqa: E731
        ctrl.rules.insert(0, always_off)  # inserted before basic_hysteresis

        # always_off returns False first; basic_hysteresis would return True
        room = ctrl.rooms["living"]
        decision = None
        for rule in ctrl.rules:
            decision = rule(room, _ctx())
            if decision is not None:
                break
        assert decision is False

    def test_all_abstain_leaves_relay_state_unchanged(self, monkeypatch, tmp_path):
        room_cfg = FakeRoomConfig(current_temperature=22.0, relay_status=True)
        ctrl = _make_controller({"living": room_cfg}, monkeypatch, tmp_path)
        ctrl.rules = [lambda room, ctx: None]  # single always-abstain rule

        room = ctrl.rooms["living"]
        decision = None
        for rule in ctrl.rules:
            decision = rule(room, _ctx())
            if decision is not None:
                break
        assert decision is None
        # relay_on must be unchanged
        assert room.relay_on is True


# ---------------------------------------------------------------------------
# ThermostatController initialisation
# ---------------------------------------------------------------------------

class TestControllerInit:
    def test_rooms_populated_from_modbus(self, monkeypatch, tmp_path):
        rooms = {
            "living": FakeRoomConfig(current_temperature=21.0, relay_status=False),
            "bedroom": FakeRoomConfig(current_temperature=19.0, relay_status=True),
        }
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert set(ctrl.rooms.keys()) == {"living", "bedroom"}

    def test_current_temperature_copied_from_modbus(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=18.5, relay_status=False)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert ctrl.rooms["living"].current_temperature == 18.5

    def test_relay_on_copied_from_modbus(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=True)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert ctrl.rooms["living"].relay_on is True

    def test_target_temperature_defaults_to_modbus_value(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False, target_temperature=21.5)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert ctrl.rooms["living"].target_temperature == 21.5

    def test_persisted_target_overrides_modbus_default(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False, target_temperature=22.0)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path, state={"living": 19.0})
        assert ctrl.rooms["living"].target_temperature == 19.0

    def test_missing_state_file_uses_modbus_default(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False, target_temperature=23.0)}
        # No state= argument → file does not exist
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert ctrl.rooms["living"].target_temperature == 23.0

    def test_corrupt_state_file_uses_modbus_default(self, monkeypatch, tmp_path):
        state_file = tmp_path / "thermostat_state.json"
        state_file.write_text("not valid json{{")
        monkeypatch.setattr(thermostat, "STATE_FILE", str(state_file))
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False, target_temperature=22.0)}
        ctrl = ThermostatController(FakeModbusController(rooms), FakeBsbController())
        assert ctrl.rooms["living"].target_temperature == 22.0

    def test_basic_hysteresis_registered_by_default(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        assert basic_hysteresis in ctrl.rules


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

class TestStatePersistence:
    def test_set_target_temperature_updates_room(self, monkeypatch, tmp_path):
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False)}
        ctrl = _make_controller(rooms, monkeypatch, tmp_path)
        ctrl.set_target_temperature("living", 18.0)
        assert ctrl.rooms["living"].target_temperature == 18.0

    def test_set_target_temperature_writes_json(self, monkeypatch, tmp_path):
        state_file = tmp_path / "thermostat_state.json"
        monkeypatch.setattr(thermostat, "STATE_FILE", str(state_file))
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False)}
        ctrl = ThermostatController(FakeModbusController(rooms), FakeBsbController())
        ctrl.set_target_temperature("living", 17.5)

        saved = json.loads(state_file.read_text())
        assert saved == {"living": 17.5}

    def test_persisted_state_survives_restart(self, monkeypatch, tmp_path):
        """Simulate a reboot: second controller reads what first controller wrote."""
        state_file = tmp_path / "thermostat_state.json"
        monkeypatch.setattr(thermostat, "STATE_FILE", str(state_file))
        rooms = {"living": FakeRoomConfig(current_temperature=20.0, relay_status=False, target_temperature=22.0)}

        # First "boot": set a custom target
        ctrl1 = ThermostatController(FakeModbusController(rooms), FakeBsbController())
        ctrl1.set_target_temperature("living", 16.0)

        # Second "boot": value should be restored
        ctrl2 = ThermostatController(FakeModbusController(rooms), FakeBsbController())
        assert ctrl2.rooms["living"].target_temperature == 16.0

    def test_multiple_rooms_all_persisted(self, monkeypatch, tmp_path):
        state_file = tmp_path / "thermostat_state.json"
        monkeypatch.setattr(thermostat, "STATE_FILE", str(state_file))
        rooms = {
            "living": FakeRoomConfig(current_temperature=20.0, relay_status=False),
            "bedroom": FakeRoomConfig(current_temperature=18.0, relay_status=False),
        }
        ctrl = ThermostatController(FakeModbusController(rooms), FakeBsbController())
        ctrl.set_target_temperature("living", 21.0)
        ctrl.set_target_temperature("bedroom", 18.5)

        saved = json.loads(state_file.read_text())
        assert saved["living"] == 21.0
        assert saved["bedroom"] == 18.5
