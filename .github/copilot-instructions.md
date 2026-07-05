# BSBcontrol — Copilot Instructions

## External libraries (ignore when analyzing implementation)
The following folders contain third-party libraries and are listed under "Distribution / packaging" in `.gitignore`. They are **not** part of the project implementation and should be excluded from code analysis, summaries, and suggestions:

- `typings/` — MicroPython stubs (dev tooling only)
- `umodbus/` — Modbus TCP master library
- `microdot/` — async HTTP server library

## Runtime debug logging
Both `bsb/protocol.py` and `bsb/controller.py` contain a `DEBUG = False` flag near the top of the file. Set it to `True` to enable diagnostic `[BSB]` print messages useful for analyzing bus communication problems:

- `[BSB] tx: GET` — outgoing GET telegram: field id, command tid, destination address, raw bytes on the wire
- `[BSB] parse:` — every telegram parsed off the bus: packet type, tid, whether the field is known, raw payload bytes, decoded value
- `[BSB] rx:` — every dispatched telegram: packet type, tid, src/dst addresses, decoded data; also logs `no pending for tid=...` when a response arrives that doesn't match any waiting request
