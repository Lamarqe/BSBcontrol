import asyncio
import json

from umodbus.tcp import TCP as ModbusTCPMaster

CONFIG_FILE = "config/modbus.json"

HYSTERESIS = 0.5  # degrees Celsius

RESET = True  # For Testing: reset all relays on startup


class ModbusDevice:
    def __init__(self, ip: str, port: int, node_id: int):
        """Initialize Modbus device with IP, port, and node ID."""
        self.master = ModbusTCPMaster(slave_ip=ip, slave_port=port)
        self.node_id = node_id


class RoomConfig:
    def __init__(
        self,
        temperature_device: ModbusDevice,
        temperature_register: int,
        relay_device: ModbusDevice,
        relay_register: int,
        target_temperature: float = 22.0,
    ):
        """Initialize room configuration with devices and registers."""
        self._temp_device: ModbusDevice = temperature_device
        self._temp_register: int = temperature_register
        self._relay_device: ModbusDevice = relay_device
        self._relay_register: int = relay_register
        self.target_temperature: float = target_temperature
        self._current_temperature: float = self._read_current_temperature()
        self._relay_status: bool = self._read_relay_status()

    def set_relay_status(self, status: bool) -> None:
        """Set the relay status."""
        self._relay_device.master.write_single_coil(
            slave_addr=self._relay_device.node_id,
            output_address=self._relay_register,
            output_value=status,
        )

    def _read_relay_status(self) -> bool:
        """Read the current status of the relay."""
        return self._relay_device.master.read_coils(
            slave_addr=self._relay_device.node_id,
            starting_addr=self._relay_register,
            coil_qty=1,
        )[0]

    @property
    def relay_status(self) -> bool:
        """Get the current relay status."""
        return self._relay_status

    def update_relay_status(self) -> None:
        """Update the relay status."""
        self._relay_status = self._read_relay_status()

    def _read_current_temperature(self) -> float:
        """Get the current temperature from the sensor."""
        temperatures = self._temp_device.master.read_input_registers(
            slave_addr=self._temp_device.node_id,
            starting_addr=self._temp_register,
            register_qty=1,
            signed=False,
        )
        return temperatures[0] / 10.0

    @property
    def current_temperature(self) -> float:
        """Get the current temperature."""
        return self._current_temperature


class ModbusController:
    def __init__(self):
        """Initialize Modbus controller from configuration file."""
        config = json.load(open(CONFIG_FILE))
        modbus_config = config["devices"]
        self.devices: dict[str, ModbusDevice] = {}
        for device_name, device_config in modbus_config.items():
            self.devices[device_name] = ModbusDevice(
                ip=device_config["ip"], port=device_config["port"], node_id=device_config["node_id"]
            )

        self.rooms: dict[str, RoomConfig] = {}
        for room_name, room_config in config["rooms"].items():
            self.rooms[room_name] = RoomConfig(
                temperature_device=self.devices[room_config["temperature_sensor"]["device"]],
                temperature_register=room_config["temperature_sensor"]["register"],
                relay_device=self.devices[room_config["relay"]["device"]],
                relay_register=room_config["relay"]["register"],
            )

    async def run(self):
        """Continously read temperature and relay statuses."""
        if RESET:
            for room in self.rooms.values():
                room.set_relay_status(False)
                await asyncio.sleep(0.5)
                room.update_relay_status()
        print("Starting Modbus controller")
        while True:
            # configure Modbus TCP master/host
            for room_name, room in self.rooms.items():
                room._current_temperature = room._read_current_temperature()

                if abs(temperature_deviation := (room._current_temperature - room.target_temperature)) < HYSTERESIS:
                    continue

                relay_updated = False
                if temperature_deviation > 0 and room.relay_status:
                    room.set_relay_status(False)
                    relay_updated = True
                elif temperature_deviation < 0 and not room.relay_status:
                    room.set_relay_status(True)
                    relay_updated = True

                if relay_updated:
                    room.update_relay_status()
                    await asyncio.sleep(0.5)  # wait a bit for the relay to update
                    print("Relay {} turned {}".format(room_name, "On" if room.relay_status else "Off"))

            await asyncio.sleep(20)
