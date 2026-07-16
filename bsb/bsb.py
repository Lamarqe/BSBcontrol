import asyncio
import gc
import json

import machine

from .fields import BsBConfigReader
from .protocol import (
    BsbCommand, BsbCommandFlags, BsbTelegram, BsbType, invert
)

CONFIG_FILE = "config/bsb.json"
TYPES_FILE  = "config/bsb-types.json"

DEBUG = False
LISTEN = False
REQUEST_TIMEOUT = 5.0
POLL_INTERVAL = 0.02


def _listen_rx(telegram):
    """Print a received BSB telegram in compact, human-readable form."""
    cmd = telegram.command
    ptype = telegram.packettype.upper()
    src = telegram.src
    dst = telegram.dst
    if cmd.bsb_type and cmd.bsb_type.name == "RAW":
        raw = " ".join("%02X" % b for b in telegram.rawdata) if telegram.rawdata else "-"
        print("[LISTEN] %s %d->%d tid=0x%08X raw=%s" % (ptype, src, dst, cmd.telegram_id, raw))
    elif telegram.packettype in ("get", "ack"):
        print("[LISTEN] %s %d->%d #%s %s" % (ptype, src, dst, cmd.parameter, cmd.disp_name))
    else:
        value = telegram.data
        if cmd.enum and isinstance(value, int) and value in cmd.enum:
            value = cmd.enum[value]
        unit = (" " + cmd.unit) if cmd.unit else ""
        print("[LISTEN] %s %d->%d #%s %s = %s%s" % (ptype, src, dst, cmd.parameter, cmd.disp_name, value, unit))


def _build_commands(fields_raw, type_meta):
    commands = {}
    commands_by_tid = {}
    for field_id, fdef in fields_raw.items():
        tid = fdef["telegram_id"]
        type_name = fdef["type"]
        meta = type_meta[type_name]
        bsb_type = BsbType(
            name=type_name,
            datatype=meta["datatype"],
            payload_length=meta["payload_length"],
            factor=meta.get("factor", 1),
            unsigned=meta.get("unsigned", False),
            unit=meta["unit"],
            enable_byte=meta["enable_byte"],
        )
        cmd = BsbCommand(
            parameter=field_id,
            telegram_id=tid,
            disp_name=fdef["name"],
            bsb_type=bsb_type,
            unit=meta["unit"],
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
        # UART2 is pre-initialized in boot.py before the network stack to secure
        # contiguous DMA memory. Here we only obtain a reference without reinstalling
        # the driver (no parameters = no uart_driver_delete/install on ESP32).
        self._uart = machine.UART(2)
        self._leftover = b""
        self._pending = {}  # tid_int -> {"event": Event, "result": list}
        self._bus_lock = asyncio.Lock()

        config = json.load(open(CONFIG_FILE))
        self.own_address = config["own_address"]
        self.dest_address = config["dest_address"]

        type_meta = json.load(open(TYPES_FILE))
        fields_raw = BsBConfigReader().load_fields(config["fields"])
        self._commands, self._commands_by_tid = _build_commands(fields_raw, type_meta)
        del type_meta, fields_raw
        gc.collect()

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
        if LISTEN:
            _listen_rx(telegram)
        if DEBUG:
            print("[BSB] rx: type=%s tid=0x%08X src=0x%02X dst=0x%02X data=%r raw=%s" % (
                telegram.packettype,
                telegram.command.telegram_id,
                telegram.src,
                telegram.dst,
                telegram.data,
                " ".join("%02X" % b for b in telegram.rawdata),
            ))
        if telegram.packettype in ("ret", "ack"):
            pending = self._pending.get(telegram.command.telegram_id)
            if pending:
                pending["result"].append(telegram)
                pending["event"].set()
            elif DEBUG:
                print("[BSB] rx: no pending for tid=0x%08X (pending keys: %s)" % (
                    telegram.command.telegram_id,
                    ["0x%08X" % k for k in self._pending],
                ))

    async def get_field(self, field_id):
        cmd = self._commands.get(field_id)
        if cmd is None:
            raise ValueError("Unknown field_id: %d" % field_id)

        async with self._bus_lock:
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
                raw_tx = telegram.serialize(validate=False)
                if LISTEN:
                    print("[LISTEN] GET %d->%d #%s %s" % (self.own_address, self.dest_address, cmd.parameter, cmd.disp_name))
                if DEBUG:
                    print("[BSB] tx: GET field=%d tid=0x%08X dst=0x%02X bytes=%s" % (
                        field_id,
                        cmd.telegram_id,
                        self.dest_address,
                        " ".join("%02X" % b for b in invert(raw_tx)),
                    ))
                self._uart.write(invert(raw_tx))
                await asyncio.wait_for(event.wait(), REQUEST_TIMEOUT)
                t = result[0]
                value = t.data
                if cmd.enum and isinstance(value, int) and value in cmd.enum:
                    value = cmd.enum[value]
                return {"id": field_id, "name": cmd.disp_name, "value": value, "unit": cmd.unit}
            finally:
                self._pending.pop(cmd.telegram_id, None)

    async def set_field(self, field_id, value):
        cmd = self._commands.get(field_id)
        if cmd is None:
            raise ValueError("Unknown field_id: %d" % field_id)

        async with self._bus_lock:
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
                if LISTEN:
                    unit = (" " + cmd.unit) if cmd.unit else ""
                    print("[LISTEN] SET %d->%d #%s %s = %s%s" % (self.own_address, self.dest_address, cmd.parameter, cmd.disp_name, value, unit))
                self._uart.write(invert(telegram.serialize()))
                await asyncio.wait_for(event.wait(), REQUEST_TIMEOUT)
                t = result[0]
                if t.packettype != "ack":
                    raise RuntimeError("Expected ACK, got %s" % t.packettype)
                return {"message": "updated"}
            finally:
                self._pending.pop(cmd.telegram_id, None)
