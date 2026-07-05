import asyncio
import json

import machine

from .fields import BsBConfigReader
from .protocol import (
    BsbCommand, BsbCommandFlags, BsbTelegram, BsbType, invert
)

CONFIG_FILE = "config/bsb.json"

_TYPE_TO_DATATYPE = {
    "ENUM": "ENUM",
    "TEMP": "VALS",
    "PERCENT": "VALS",
    "PERCENT_NN": "VALS",
}

REQUEST_TIMEOUT = 5.0
POLL_INTERVAL = 0.02


def _tid_int(tid_bytes):
    return (tid_bytes[0] << 24) | (tid_bytes[1] << 16) | (tid_bytes[2] << 8) | tid_bytes[3]


def _build_commands(fields_raw):
    commands = {}
    commands_by_tid = {}
    for field_id, fdef in fields_raw.items():
        tid = _tid_int(fdef["telegram_id"])
        type_name = fdef["type"]
        bsb_type = BsbType(
            name=type_name,
            datatype=_TYPE_TO_DATATYPE[type_name],
            payload_length=fdef["payload_length"],
            factor=fdef["factor"],
            unsigned=fdef["unsigned"],
            unit=fdef["unit"],
            enable_byte=6 if fdef["nullable"] else 1,
        )
        cmd = BsbCommand(
            parameter=field_id,
            telegram_id=tid,
            disp_name=fdef["name"],
            bsb_type=bsb_type,
            unit=fdef["unit"],
            enum=fdef["enum"],
            min_value=fdef["min_value"],
            max_value=fdef["max_value"],
            flags=BsbCommandFlags.Readonly if fdef["readonly"] else 0,
        )
        commands[field_id] = cmd
        commands_by_tid[tid] = cmd
    return commands, commands_by_tid


class BsbController:
    def __init__(self):
        config = json.load(open(CONFIG_FILE))
        self.own_address = config["own_address"]
        self.dest_address = config["dest_address"]

        fields_raw = BsBConfigReader().load_fields(config["fields"])
        self._commands, self._commands_by_tid = _build_commands(fields_raw)

        self._uart = machine.UART(2, rx=36, tx=5, baudrate=4800, parity=1, stop=1, bits=8)
        self._leftover = b""
        self._pending = {}  # tid_int -> {"event": Event, "result": list}

    async def run(self):
        print("Starting BSB controller")
        while True:
            n = self._uart.any()
            if n > 0:
                raw = invert(self._uart.read(n))
                self._leftover += raw
                self._process_buffer()
            await asyncio.sleep(POLL_INTERVAL)

    def _process_buffer(self):
        results = BsbTelegram.deserialize(self._leftover, self._commands_by_tid)

        # Keep all trailing non-telegram items as leftover (may be an incomplete telegram)
        leftover = b""
        for item in reversed(results):
            if isinstance(item, BsbTelegram):
                break
            leftover = item[0] + leftover
        self._leftover = leftover

        for item in results:
            if isinstance(item, BsbTelegram):
                self._dispatch(item)

    def _dispatch(self, telegram):
        if telegram.packettype in ("ret", "ack"):
            pending = self._pending.get(telegram.command.telegram_id)
            if pending:
                pending["result"].append(telegram)
                pending["event"].set()

    async def get_field(self, field_id):
        cmd = self._commands.get(field_id)
        if cmd is None:
            raise ValueError("Unknown field_id: %d" % field_id)

        event = asyncio.Event()
        result = []
        self._pending[cmd.telegram_id] = {"event": event, "result": result}

        try:
            telegram = BsbTelegram(
                command=cmd,
                src=self.own_address,
                dst=self.dest_address,
                packettype="get",
            )
            self._uart.write(invert(telegram.serialize(validate=False)))
            await asyncio.wait_for(event.wait(), REQUEST_TIMEOUT)
            t = result[0]
            return {"id": field_id, "name": cmd.disp_name, "value": t.data, "unit": cmd.unit}
        finally:
            self._pending.pop(cmd.telegram_id, None)

    async def set_field(self, field_id, value):
        cmd = self._commands.get(field_id)
        if cmd is None:
            raise ValueError("Unknown field_id: %d" % field_id)

        event = asyncio.Event()
        result = []
        self._pending[cmd.telegram_id] = {"event": event, "result": result}

        try:
            telegram = BsbTelegram(
                command=cmd,
                src=self.own_address,
                dst=self.dest_address,
                packettype="set",
                data=value,
            )
            self._uart.write(invert(telegram.serialize()))
            await asyncio.wait_for(event.wait(), REQUEST_TIMEOUT)
            t = result[0]
            if t.packettype != "ack":
                raise RuntimeError("Expected ACK, got %s" % t.packettype)
            return {"message": "updated"}
        finally:
            self._pending.pop(cmd.telegram_id, None)
