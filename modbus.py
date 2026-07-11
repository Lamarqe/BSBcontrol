import json

from umodbus.tcp import TCP as ModbusTCPMaster

CONFIG_FILE = "config/modbus.json"


class ModbusDevice:
    def __init__(self, ip: str, port: int, node_id: int):
        """Initialize Modbus device with IP, port, and node ID."""
        self._ip = ip
        self._port = port
        self.node_id = node_id
        self.master = ModbusTCPMaster(slave_ip=ip, slave_port=port)

    def reconnect(self) -> None:
        """Close the existing socket and open a fresh TCP connection."""
        try:
            self.master._sock.close()
        except Exception:
            pass
        self.master = ModbusTCPMaster(slave_ip=self._ip, slave_port=self._port)


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

    def set_relay_status(self, status: bool) -> bool:
        """Set the relay status and return the value written.

        Raises OSError if the device does not confirm the write.
        """
        success = self._relay_device.master.write_single_coil(
            slave_addr=self._relay_device.node_id,
            output_address=self._relay_register,
            output_value=status,
        )
        if not success:
            raise OSError("write_single_coil not confirmed by device")
        self._relay_status = status
        return status

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


