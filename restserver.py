import asyncio
import json

import modbus
import tinyweb


class CurrentTemperature:
    def __init__(self, rooms: dict[str, modbus.RoomConfig]):
        self.rooms = rooms

    def not_found(self):
        return {"message": "no such room"}, 404

    def get(self, data, room_name):
        """Get current temperature for given room"""
        if room_name not in self.rooms:
            return self.not_found()
        return json.dumps({"current_temperature": self.rooms[room_name].current_temperature})


class TargetTemperature:
    def __init__(self, rooms: dict[str, modbus.RoomConfig]):
        self.rooms = rooms

    def not_found(self):
        return {"message": "no such room"}, 404

    def get(self, data, room_name):
        """Get target temperature for given room"""
        if room_name not in self.rooms:
            return self.not_found()
        return json.dumps({"target_temperature": self.rooms[room_name].target_temperature})

    def post(self, data, room_name):
        """Update given customer"""
        if room_name not in self.rooms:
            return self.not_found()
        print("Post data:", data)
        self.rooms[room_name].target_temperature = data["target_temperature"]
        return {"message": "updated"}


class RestServer:
    def __init__(self, modbus_controller: modbus.ModbusController):
        self.modbus_controller = modbus_controller

    async def run(self):
        try:
            web_server = tinyweb.webserver()

            @web_server.route("/")
            async def index(request, response):
                await response.start_html()
                await response.send("<h1>Welcome to the Modbus REST Server</h1>")

            web_server.add_resource(TargetTemperature(self.modbus_controller.rooms), "/target_temperature/<room>")
            web_server.add_resource(CurrentTemperature(self.modbus_controller.rooms), "/current_temperature/<room>")

            web_server.run(host="0.0.0.0", port=80, loop_forever=False)
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            print("webserver shall be cancelled")
            web_server.shutdown()
            await asyncio.sleep(1)
            print("Webserver task was cancelled")
            raise
