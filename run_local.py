"""
Local development runner for MicroPython Unix port.

Patches machine.UART before bsb.py imports it, then starts the application.
BSB GET/SET requests will time out (no real UART). Modbus TCP requests will
fail to connect unless the real devices are reachable on the local network.

Run with:
    sudo micropython run_local.py          # port 8080
    micropython run_local.py 8081          # custom port
"""

import sys


class _MockUART:
    def __init__(self, *args, **kwargs):
        print("[MockUART] init", args, kwargs)

    def any(self):
        return 0

    def read(self, n=None):
        return b""

    def write(self, data):
        return len(data)


class _MockMachine:
    UART = _MockUART


# Inject BEFORE any import that transitively does `import machine`.
# MicroPython checks sys.modules first, so this shadows the built-in C module.
sys.modules["machine"] = _MockMachine()

import asyncio

# Optionally override the listen port via command-line argument
_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

import restserver as _rs
_orig_run = _rs.RestServer.run


async def _patched_run(self):
    try:
        await self.app.start_server(host="0.0.0.0", port=_PORT)
    except asyncio.CancelledError:
        print("webserver shall be cancelled")
        await self.app.shutdown()
        await asyncio.sleep(1)
        print("Webserver task was cancelled")
        raise


_rs.RestServer.run = _patched_run

import main

asyncio.run(main.async_main())
