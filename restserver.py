import asyncio

import bsb
import modbus
from microdot import Microdot


class RestServer:
    def __init__(self, modbus_controller: modbus.ModbusController, bsb_controller: bsb.BsbController):
        self.modbus_controller = modbus_controller
        self.bsb_controller = bsb_controller
        self.app = Microdot()

        @self.app.route("/")
        async def index(request):
            return "<h1>Welcome to the Modbus REST Server</h1>", 200, {"Content-Type": "text/html"}

        @self.app.route("/current_temperature/<room>", methods=["GET"])
        async def get_current_temperature(request, room):
            if room not in self.modbus_controller.rooms:
                return {"message": "no such room"}, 404
            return {"current_temperature": self.modbus_controller.rooms[room].current_temperature}

        @self.app.route("/target_temperature/<room>", methods=["GET"])
        async def get_target_temperature(request, room):
            if room not in self.modbus_controller.rooms:
                return {"message": "no such room"}, 404
            return {"target_temperature": self.modbus_controller.rooms[room].target_temperature}

        @self.app.route("/target_temperature/<room>", methods=["POST"])
        async def post_target_temperature(request, room):
            if room not in self.modbus_controller.rooms:
                return {"message": "no such room"}, 404
            self.modbus_controller.rooms[room].target_temperature = request.json["target_temperature"]
            return {"message": "updated"}

        @self.app.route("/bsb/field/<field_id>", methods=["GET"])
        async def get_bsb_field(request, field_id):
            try:
                result = await self.bsb_controller.get_field(int(field_id))
            except ValueError:
                return {"message": "unknown field"}, 404
            except asyncio.TimeoutError:
                return {"message": "timeout"}, 504
            return result

        @self.app.route("/bsb/field/<field_id>", methods=["POST"])
        async def post_bsb_field(request, field_id):
            try:
                result = await self.bsb_controller.set_field(int(field_id), request.json["value"])
            except ValueError as e:
                return {"message": str(e)}, 404
            except asyncio.TimeoutError:
                return {"message": "timeout"}, 504
            return result

    async def run(self):
        try:
            while True:
                try:
                    await self.app.start_server(host="0.0.0.0", port=80)
                    break
                except OSError as e:
                    if e.args[0] == 112:  # EADDRINUSE
                        print("Port 80 in use, retrying in 5s...")
                        await asyncio.sleep(5)
                    else:
                        raise
        except asyncio.CancelledError:
            print("webserver shall be cancelled")
            await self.app.shutdown()
            await asyncio.sleep(1)
            print("Webserver task was cancelled")
            raise
