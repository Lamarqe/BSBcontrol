import asyncio
import re

from bsb.bsb import BsbController
from thermostat import ThermostatController
from microdot import Microdot


class RestServer:
    def __init__(self, thermostat_controller: ThermostatController, bsb_controller: BsbController):
        # thermostat_controller may be None if Modbus initialization hasn't
        # completed yet; it is attached later once it becomes available.
        self.thermostat_controller = thermostat_controller
        self.bsb_controller = bsb_controller
        self.app = Microdot()



        @self.app.route("/")
        async def index(request):
            return "<h1>Welcome to the Modbus REST Server</h1>", 200, {"Content-Type": "text/html"}

        @self.app.route("/current_temperature/<room>", methods=["GET"])
        async def get_current_temperature(request, room):
            matching_rooms, error = self.resolve_rooms(room)
            if error:
                return error
            return {
                "current_temperature": {
                    room_name: room_state.current_temperature
                    for room_name, room_state in matching_rooms.items()
                }
            }

        @self.app.route("/target_temperature/<room>", methods=["GET"])
        async def get_target_temperature(request, room):
            matching_rooms, error = self.resolve_rooms(room)
            if error:
                return error
            return {
                "target_temperature": {
                    room_name: room_state.target_temperature
                    for room_name, room_state in matching_rooms.items()
                }
            }

        @self.app.route("/target_temperature/update", methods=["POST"])
        async def post_target_temperature(request):
            if self.thermostat_controller is None:
                return {"message": "thermostat not ready"}, 503
            try:
                target_temperatures = request.json["target_temperature"]
                if not isinstance(target_temperatures, dict):
                    raise TypeError
            except (KeyError, TypeError):
                return {"message": "invalid target temperatures"}, 400
            if any(
                not isinstance(target_temperature, (int, float))
                or isinstance(target_temperature, bool)
                for target_temperature in target_temperatures.values()
            ):
                return {"message": "invalid target temperatures"}, 400
            unknown_rooms = [
                room_name
                for room_name in target_temperatures
                if room_name not in self.thermostat_controller.rooms
            ]
            if unknown_rooms:
                return {"message": "no such room: {}".format(unknown_rooms[0])}, 404
            for room_name, target_temperature in target_temperatures.items():
                self.thermostat_controller.set_target_temperature(room_name, target_temperature)
            return {"message": "updated"}

        @self.app.route("/relay_status/<room>", methods=["GET"])
        async def get_relay_status(request, room):
            matching_rooms, error = self.resolve_rooms(room)
            if error:
                return error
            return {
                "relay_status": {
                    room_name: room_state.relay_on
                    for room_name, room_state in matching_rooms.items()
                }
            }

        @self.app.route("/bsb/field/<field_id>", methods=["GET"])
        async def get_bsb_field(request, field_id):
            try:
                result = await self.bsb_controller.get_field(int(field_id))
            except ValueError:
                return {"message": "unknown field"}, 404
            except asyncio.TimeoutError:
                return {"message": "timeout"}, 504
            except OSError as e:
                return {"message": "bus error: {}".format(e)}, 503
            return result

        @self.app.route("/bsb/field/<field_id>", methods=["POST"])
        async def post_bsb_field(request, field_id):
            try:
                result = await self.bsb_controller.set_field(int(field_id), request.json["value"])
            except ValueError as e:
                return {"message": str(e)}, 404
            except asyncio.TimeoutError:
                return {"message": "timeout"}, 504
            except OSError as e:
                return {"message": "bus error: {}".format(e)}, 503
            return result

    def matching_rooms(self, room_regexp):
        pattern = re.compile(room_regexp)
        return {
            room_name: room
            for room_name, room in self.thermostat_controller.rooms.items()
            if pattern.search(room_name)
        }

    def resolve_rooms(self, room_regexp):
        if self.thermostat_controller is None:
            return None, ({"message": "thermostat not ready"}, 503)
        try:
            matching_rooms = self.matching_rooms(room_regexp)
        except Exception:
            return None, ({"message": "invalid room regexp"}, 400)
        if not matching_rooms:
            return None, ({"message": "no such room"}, 404)
        return matching_rooms, None

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
