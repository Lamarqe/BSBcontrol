# BSBcontrol — Copilot Instructions

## External libraries (ignore when analyzing implementation)
The following folders contain third-party libraries and are listed under "Distribution / packaging" in `.gitignore`. They are **not** part of the project implementation and should be excluded from code analysis, summaries, and suggestions:

- `typings/` — MicroPython stubs (dev tooling only)
- `umodbus/` — Modbus TCP master library
- `microdot/` — async HTTP server library
