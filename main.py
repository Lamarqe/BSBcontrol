import asyncio
import time

from bsb import bsb
import restserver

import modbus
import thermostat
import sys


MODBUS_RETRY_INTERVAL = 10  # seconds between connection attempts


async def async_main():
    try:
        bsb_controller = bsb.BsbController()
        bsb_task = asyncio.create_task(bsb_controller.run())

        while True:
            try:
                modbus_controller = modbus.ModbusController()
                thermostat_controller = thermostat.ThermostatController(modbus_controller, bsb_controller)
                break
            except OSError as e:
                print("Modbus init failed ({}), retrying in {} s...".format(e, MODBUS_RETRY_INTERVAL))
                await asyncio.sleep(MODBUS_RETRY_INTERVAL)

        thermostat_task = asyncio.create_task(thermostat_controller.run())
        rest_server = restserver.RestServer(thermostat_controller, bsb_controller)
        rest_task = asyncio.create_task(rest_server.run())
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        print("Main task shall be cancelled")
        rest_task.cancel()
        try:
            await rest_task
        except asyncio.CancelledError:
            pass
        bsb_task.cancel()
        try:
            await bsb_task
        except asyncio.CancelledError:
            pass
        thermostat_task.cancel()
        try:
            await thermostat_task
        except asyncio.CancelledError:
            pass
        print("Main task was cancelled")
        raise


def main():
    """Main entry point of the program."""
    print("Starting main program")
    loop = asyncio.get_event_loop()
    # Install exception handler to capture unhandled task exceptions with tracebacks
    def _handle_exception(loop, context):
        exc = context.get("exception")
        print("Error occurred, exiting: {}".format(repr(exc)))
        sys.print_exception(exc)

    loop.set_exception_handler(_handle_exception)
    main_task = loop.create_task(async_main())

    try:
        loop.run_forever()
    except Exception as e:
        print("Error occurred, exiting: {}".format(repr(e)))
        sys.print_exception(e)
    except KeyboardInterrupt:
        print("Program interrupted by the user. Exiting...")
    finally:
        main_task.cancel()
        loop.close()


if __name__ == "__main__":
    main()
