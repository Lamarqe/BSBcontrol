"""conftest.py — workspace-wide test configuration.

Stubs MicroPython-only modules that cannot be imported on a desktop Python
interpreter.  These stubs are inserted into sys.modules before any test
module is collected, so imports of thermostat / modbus / bsb succeed even
though the real micropython / machine modules are not installed.
"""

import sys
from types import ModuleType


def _stub(name: str, **attrs) -> ModuleType:
    m = ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# micropython.const is used as a no-op decorator in umodbus
_stub("micropython", const=lambda x: x)

# machine.UART is used in bsb/bsb.py (not needed for thermostat tests,
# but ensures the module tree can be imported without errors)
_uart_cls = type("UART", (), {"__init__": lambda self, *a, **kw: None,
                               "any": lambda self: 0,
                               "read": lambda self, n: b"",
                               "write": lambda self, b: None})
_stub("machine", UART=_uart_cls)
