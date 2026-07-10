"""Tests for get_field() enum resolution in bsb/bsb.py.

get_field() is async and UART-driven, so we test the enum-resolution logic
that sits between t.data (raw int from the protocol layer) and the returned
dict.  The approach: patch asyncio.wait_for and the UART write so the
coroutine completes immediately with a fake telegram carrying known data.
"""

import asyncio
import pytest

from bsb.protocol import BsbCommand, BsbType, BsbDatatype, BsbCommandFlags, BsbTelegram


# ---------------------------------------------------------------------------
# Minimal BsbController stand-in that exercises the real get_field() code path
# ---------------------------------------------------------------------------

def _make_enum_cmd(enum: dict):
    """Build a BsbCommand for an ENUM field with the given enum dict."""
    bsb_type = BsbType(
        name="ENUM",
        datatype=BsbDatatype.Enum,
        payload_length=1,
        factor=1,
        unsigned=True,
        unit="",
        enable_byte=1,
    )
    return BsbCommand(
        parameter=700,
        telegram_id=0x2D3D0574,
        disp_name="Betriebsart",
        bsb_type=bsb_type,
        unit="",
        enum=enum,
    )


def _make_vals_cmd():
    """Build a BsbCommand for a TEMP (Vals) field with no enum."""
    bsb_type = BsbType(
        name="TEMP",
        datatype=BsbDatatype.Vals,
        payload_length=2,
        factor=64,
        unsigned=False,
        unit="°C",
        enable_byte=1,
    )
    return BsbCommand(
        parameter=710,
        telegram_id=0x2D3D0575,
        disp_name="Komfort-Sollwert",
        bsb_type=bsb_type,
        unit="°C",
        enum=None,
    )


class _FakeTelegram:
    """Stand-in for BsbTelegram with just the data we need."""
    def __init__(self, data, packettype="ret"):
        self.data = data
        self.packettype = packettype


class _FakeUART:
    def any(self): return 0
    def read(self, n): return b""
    def write(self, b): pass


def _make_controller_returning(cmd, fake_data):
    """
    Build a real BsbController whose get_field() will return immediately
    with fake_data injected directly into _pending, bypassing UART entirely.
    """
    import bsb.bsb as bsb_mod
    import unittest.mock as mock

    # Patch machine.UART before BsbController.__init__ runs
    import machine
    machine.UART = lambda *a, **kw: _FakeUART()

    config = {"own_address": 66, "dest_address": 0, "fields": []}
    type_meta = {}

    with mock.patch("builtins.open"), \
         mock.patch("json.load", side_effect=[config, type_meta]), \
         mock.patch("bsb.fields.BsBConfigReader.load_fields", return_value={}):
        ctrl = bsb_mod.BsbController()

    # Manually install the command
    ctrl._commands[cmd.parameter] = cmd
    ctrl._commands_by_tid[cmd.telegram_id] = cmd

    # Intercept wait_for to inject the fake telegram instead of waiting on UART
    async def _inject(coro, timeout):
        pending = ctrl._pending.get(cmd.telegram_id)
        if pending is not None:
            pending["result"].append(_FakeTelegram(fake_data))
            pending["event"].set()
        await coro  # completes immediately since event is already set

    return ctrl, _inject


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_field_enum_known_value_resolved():
    """Raw int 1 for an ENUM field should be resolved to its label string."""
    enum = {0: "Schutz", 1: "Automatik", 3: "Komfort"}
    cmd = _make_enum_cmd(enum=enum)
    ctrl, inject = _make_controller_returning(cmd, fake_data=1)

    import asyncio as _asyncio
    original = _asyncio.wait_for
    _asyncio.wait_for = inject
    try:
        result = _run(ctrl.get_field(700))
    finally:
        _asyncio.wait_for = original

    assert result["value"] == "Automatik"
    assert result["id"] == 700
    assert result["name"] == "Betriebsart"


def test_get_field_enum_unknown_value_returned_as_int():
    """If the raw int is not in the enum dict, return it unchanged."""
    enum = {0: "Schutz", 1: "Automatik"}
    cmd = _make_enum_cmd(enum=enum)
    ctrl, inject = _make_controller_returning(cmd, fake_data=99)

    import asyncio as _asyncio
    original = _asyncio.wait_for
    _asyncio.wait_for = inject
    try:
        result = _run(ctrl.get_field(700))
    finally:
        _asyncio.wait_for = original

    assert result["value"] == 99


def test_get_field_no_enum_returns_raw_value():
    """For a non-enum field (TEMP), the numeric value passes through unchanged."""
    cmd = _make_vals_cmd()
    ctrl, inject = _make_controller_returning(cmd, fake_data=22.0)

    import asyncio as _asyncio
    original = _asyncio.wait_for
    _asyncio.wait_for = inject
    try:
        result = _run(ctrl.get_field(710))
    finally:
        _asyncio.wait_for = original

    assert result["value"] == 22.0


def test_get_field_enum_zero_value_resolved():
    """Enum value 0 (falsy) must still be resolved correctly."""
    enum = {0: "Schutz", 1: "Automatik"}
    cmd = _make_enum_cmd(enum=enum)
    ctrl, inject = _make_controller_returning(cmd, fake_data=0)

    import asyncio as _asyncio
    original = _asyncio.wait_for
    _asyncio.wait_for = inject
    try:
        result = _run(ctrl.get_field(700))
    finally:
        _asyncio.wait_for = original

    assert result["value"] == "Schutz"

