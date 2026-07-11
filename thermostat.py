import asyncio
import json
import os

import modbus

POLL_INTERVAL = 30   # seconds
HYSTERESIS = 0.5     # degrees Celsius
STATE_FILE = "state/thermostat_state.json"


class RoomState:
    def __init__(self, name: str, current_temperature: float, target_temperature: float, relay_on: bool):
        self.name = name
        self.current_temperature = current_temperature
        self.target_temperature = target_temperature
        self.relay_on = relay_on


class SystemContext:
    def __init__(self, bsb_data: dict, energy_price=None):
        self.bsb_data = bsb_data
        self.energy_price = energy_price


def basic_hysteresis(room: RoomState, ctx: SystemContext):
    """Turn relay ON when room is too cold, OFF when too warm; abstain inside the dead band."""
    deviation = room.current_temperature - room.target_temperature
    if abs(deviation) < HYSTERESIS:
        return None  # inside dead band — keep current state
    return deviation < 0  # True = too cold → ON, False = too warm → OFF


class ThermostatController:
    def __init__(self, modbus_ctrl: modbus.ModbusController, bsb_ctrl):
        self._modbus = modbus_ctrl
        self._bsb = bsb_ctrl
        self.rules = [basic_hysteresis]

        persisted = self._load_state()
        self.rooms: dict[str, RoomState] = {}
        for room_name, room_cfg in self._modbus.rooms.items():
            target = persisted.get(room_name, room_cfg.target_temperature)
            self.rooms[room_name] = RoomState(
                name=room_name,
                current_temperature=room_cfg.current_temperature,
                target_temperature=target,
                relay_on=room_cfg.relay_status,
            )

    def _load_state(self) -> dict:
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            os.mkdir("state")
        except OSError:
            pass  # directory already exists
        with open(STATE_FILE, "w") as f:
            json.dump(
                {name: room.target_temperature for name, room in self.rooms.items()},
                f,
            )

    def set_target_temperature(self, room_name: str, temp: float) -> None:
        self.rooms[room_name].target_temperature = temp
        self._save_state()

    async def run(self) -> None:
        print("Starting Thermostat controller")
        while True:
            # 1. Refresh temperatures from hardware
            for room_name, room_cfg in self._modbus.rooms.items():
                try:
                    room_cfg._current_temperature = room_cfg._read_current_temperature()
                    room = self.rooms[room_name]
                    room.current_temperature = room_cfg.current_temperature
                except OSError as e:
                    print("WARNING: temperature read failed for {}: {}".format(room_name, e))
                    try:
                        room_cfg._temp_device.reconnect()
                    except OSError as re:
                        print("WARNING: reconnect failed for {}: {}".format(room_name, re))
                await asyncio.sleep(0)  # yield after each room so Microdot can run

            # 2. Build system context (BSB data and energy price reserved for future rules)
            ctx = SystemContext(bsb_data={}, energy_price=None)

            # 3. Evaluate rule chain for each room
            for room_name, room in self.rooms.items():
                decision = None
                for rule in self.rules:
                    decision = rule(room, ctx)
                    if decision is not None:
                        break

                if decision is None:
                    continue  # all rules abstained — leave relay unchanged

                if decision != room.relay_on:
                    room_cfg = self._modbus.rooms[room_name]
                    try:
                        room.relay_on = room_cfg.set_relay_status(decision)
                        print("Relay {} turned {}".format(room_name, "On" if room.relay_on else "Off"))
                    except OSError as e:
                        print("WARNING: relay write failed for {}: {}".format(room_name, e))

            await asyncio.sleep(POLL_INTERVAL)
