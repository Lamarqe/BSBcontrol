import asyncio
import time

import restserver

import modbus


async def async_main():
    try:
        while True:
            modbus_controller = modbus.ModbusController()
            modbus_task = asyncio.create_task(modbus_controller.run())
            rest_server = restserver.RestServer(modbus_controller)
            rest_task = asyncio.create_task(rest_server.run())
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        print("Main task shall be cancelled")
        rest_task.cancel()
        try:
            await rest_task
        except asyncio.CancelledError:
            pass
        modbus_task.cancel()
        try:
            await modbus_task
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
        print("Error occurred, exiting: ", e)
    except KeyboardInterrupt:
        print("Program interrupted by the user. Exiting...")
    finally:
        main_task.cancel()
        loop.close()


if __name__ == "__main__":
    main()
