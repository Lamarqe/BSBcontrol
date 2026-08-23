import asyncio
import time

import machine

from bsb import bsb
import restserver

import modbus
import thermostat
import sys


MODBUS_RETRY_INTERVAL = 300  # seconds between connection attempts


async def async_main():
    thermostat_task = None
    try:
        bsb_controller = bsb.BsbController()
        bsb_task = asyncio.create_task(bsb_controller.run())

        # Start the REST server right away (BSB endpoints don't depend on Modbus),
        # attaching the thermostat controller once Modbus init below succeeds.
        rest_server = restserver.RestServer(None, bsb_controller)
        rest_task = asyncio.create_task(rest_server.run())

        # Build the device/room tree once (no I/O yet) and keep retrying
        # connect() on this same instance, so failed attempts don't leak
        # a fresh set of sockets on every retry cycle.
        modbus_controller = modbus.ModbusController()
        while True:
            try:
                await modbus_controller.connect()
                thermostat_controller = thermostat.ThermostatController(modbus_controller, bsb_controller)
                break
            except OSError as e:
                print("Modbus init failed ({}), retrying in {} s...".format(e, MODBUS_RETRY_INTERVAL))
                await asyncio.sleep(MODBUS_RETRY_INTERVAL)

        rest_server.thermostat_controller = thermostat_controller
        thermostat_task = asyncio.create_task(thermostat_controller.run())

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
        if thermostat_task is not None:
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
    main_task = loop.create_task(async_main())

    try:
        loop.run_forever()
    except Exception as e:
        print("Error occurred, exiting: {}".format(repr(e)))
        sys.print_exception(e)
        main_task.cancel()
        loop.close()
        print("Rebooting due to unhandled error in main event loop...")
        machine.reset()
    except KeyboardInterrupt:
        print("Program interrupted by the user. Exiting...")
        main_task.cancel()
        loop.close()


if __name__ == "__main__":
    main()
