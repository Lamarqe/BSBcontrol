# BSBcontrol Architecture

ESP32-based MicroPython thermostat controller with Modbus TCP, BSB boiler bus, and REST API.

## Hardware
- **MCU**: Olimex ESP32-POE with LAN8720 Ethernet PHY (pins: MDC=23, MDIO=18, PWR=12, REF_CLK=17)
- **Network**: Static IP (configured in `config/network.json`); prefers wired LAN, falls back to Wi-Fi
- **Temperature sensor**: Volistartion EDM-1780B — Modbus TCP, input register, value ÷ 10 = °C
- **Relay board**: Waveshare Modbus PoE Ethernet Relay (C) — single coil per relay
- **BSB adapter**: BSB-LAN compatible adapter on UART2 (RX=GPIO36, TX=GPIO5)

## Files
| File | Purpose |
|------|---------|
| `boot.py` | Network init (LAN → Wi-Fi fallback), WebREPL start |
| `main.py` | Async entry point; launches `ModbusController`, `BsbController`, `RestServer` tasks |
| `modbus.py` | Thermostat logic: reads temps, drives relays via Modbus TCP |
| `bsb.py` | BSB boiler bus controller: UART comms, GET/SET field requests |
| `bsb_protocol.py` | BSB protocol layer: telegram parse/serialize, CRC16, payload encode/decode |
| `bsb_fields.py` | Loads BSB field definitions from device model JSON for whitelisted field IDs |
| `restserver.py` | HTTP REST API (microdot, port 80) |
| `config/modbus.json` | Modbus device + room mapping |
| `config/network.json` | IP config + Wi-Fi credentials |
| `config/bsb.json` | BSB own/dest address and whitelisted field ID list |

## Async Architecture
All three subsystems run as concurrent `asyncio` tasks under a single event loop:

```
main.py
├── ModbusController.run()   — polls Modbus TCP every 20 s
├── BsbController.run()      — polls UART every 20 ms, dispatches telegrams
└── RestServer.run()         — microdot HTTP server, awaits BSB/Modbus on each request
```

The REST server routes `await` directly into `BsbController.get_field()` / `set_field()`, which suspend on `asyncio.Event` until the BSB response telegram arrives (or a 5 s timeout expires). This keeps the HTTP handler and the UART reader decoupled with no shared mutable state beyond the `_pending` dict.

**Shutdown order** (on `CancelledError`): REST → BSB → Modbus. The REST server is stopped first so no new requests can arrive while the lower layers are tearing down.

## Control Logic (`modbus.py`)
- Poll interval: **20 s**
- Hysteresis: **±0.5 °C**
- Relay **ON** (heating) when `current_temp < target_temp − 0.5`
- Relay **OFF** when `current_temp > target_temp + 0.5`
- Default target: **22.0 °C**
- On startup: all relays reset to OFF (`RESET = True`)

## BSB Protocol Layer (`bsb_protocol.py`)
Ported from [bsbgateway](https://github.com/loehnertj/bsbgateway); adapted for MicroPython:

- **Transport**: UART2, 4800 baud, 8 data bits, odd parity, 1 stop bit
- **Byte inversion**: all bytes XOR 0xFF before transmit and after receive (BSB-LAN adapter requirement)
- **Telegram format**: `0xDC` start byte, src/dst addresses, 1-byte packet type, 4-byte command ID, variable payload, 2-byte CRC16-XMODEM
- **Packet types used**: `get` (6), `ret` (7), `set` (3), `ack` (4)
- **Payload datatypes supported**:

| Datatype | Decode result | Encode input |
|----------|--------------|--------------|
| `Vals` | `int` or `float` (divided by `factor`) | `int` / `float` |
| `Enum` | `int` (raw byte value) | `int` |
| `Bits` | `bytes` (raw payload) | `bytes` |
| `Datetime` | `(year, month, day, hour, minute, second)` | same tuple |
| `DayMonth` / `VACATIONPROG` | `(month, day)` | same tuple |
| `Time` | `(hour, minute, second)` | same tuple |
| `HourMinutes` | `(hour, minute)` | same tuple |
| `String` | `str` (latin-1, null-stripped) | `str` |
| `TimeProgram` | `[((h1,m1),(h2,m2)), ...]` up to 3 entries | same list |
| `YEAR` (name override) | `int` (year) | `int` |
| `Raw` / unknown | `bytes` | `bytes` |

  Date/time types use plain tuples instead of `datetime.datetime`/`datetime.time` (those modules are absent in MicroPython).  
  `TimeProgram` disabled slots (`0x80` marker) are skipped on decode; encode pads unused slots with `0x80 00 00 00`.  
  `String` and `TimeProgram` have no flag byte on the wire; all other types carry a 1-byte flag prefix (`0x00` = value, `0x01`/`0x05`/`0x06` = null or set variants).

- **`attrs`/`cattr` absent in MicroPython** — all model classes replaced with plain `__init__`-based classes

## BSB Controller (`bsb.py`)
- Loads `config/bsb.json` (own address `0x42`, dest `0x00`, field whitelist)
- Loads field definitions via `bsb_fields.load_fields()` at startup (synchronous, before event loop)
- Builds two lookup dicts: `_commands[field_id]` and `_commands_by_tid[telegram_id_int]`
- `telegram_id` stored as `int` (required by `serialize()` bitwise ops); converted from the 4-byte representation returned by `bsb_fields`
- UART polled every **20 ms** — keeps telegram fragmentation low at 4800 baud (≈2 ms/byte, typical telegram ≈22–40 ms)
- Incomplete telegrams preserved as `_leftover` between poll cycles (trailing non-`BsbTelegram` items from `deserialize()`)
- Pending requests keyed by `telegram_id_int`; response matched on `ret`/`ack` packet type

## BSB Field Model (`bsb_fields.py`)
- Reads `bsbgateway/devices/my_personal_device.json` and `bsbgateway/src/bsbgateway/bsb/bsb-types.json`
- Extracts only whitelisted field IDs — avoids loading the full (large) device model on the ESP32
- Resolves type definitions, global enum references, and I18nstr names (prefers "DE", falls back to "EN")
- Returns compact dicts; `bsb.py` converts these to `BsbCommand`/`BsbType` objects

## REST API (`restserver.py`)
Replaced `tinyweb` with **microdot** for native async support, cleaner JSON handling, and active maintenance.

| Method | Endpoint | Body / Response |
|--------|----------|-----------------|
| GET | `/current_temperature/<room>` | `{"current_temperature": float}` |
| GET | `/target_temperature/<room>` | `{"target_temperature": float}` |
| POST | `/target_temperature/<room>` | `{"target_temperature": float}` → `{"message": "updated"}` |
| GET | `/bsb/field/<id>` | `{"id": int, "name": str, "value": any, "unit": str}` |
| POST | `/bsb/field/<id>` | `{"value": any}` → `{"message": "updated"}` |

Room names match keys in `config/modbus.json`. Field IDs match keys in `config/bsb.json`.

All route handlers are `async def`; dicts returned directly (microdot auto-serializes to JSON).

`RestServer.__init__` takes both `modbus_controller` and `bsb_controller`. BSB routes convert the URL `<field_id>` string to `int` and return `404` for unknown field IDs or `504` on BSB bus timeout.

## External Libraries (not in repo)
- `umodbus/` — Modbus TCP master
- `tinyweb/` — async HTTP server (superseded by microdot, kept on filesystem)
- `typings/` — MicroPython stubs (dev only)
