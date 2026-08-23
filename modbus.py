import json

from umodbus.asynchronous.tcp import AsyncTCP as ModbusTCPMaster

CONFIG_FILE = "config/modbus.json"


class ModbusDevice:
    def __init__(self, ip: str, port: int, node_id: int):
        """Initialize Modbus device with IP, port, and node ID."""
        self._ip = ip
        self._port = port
        self.node_id = node_id
        self.master = ModbusTCPMaster(slave_ip=ip, slave_port=port)

    async def connect(self) -> None:
        """Open (or, if already open, close and re-open) the TCP connection.

        AsyncTCP.connect() closes any previously open writer itself, so this
        also serves as the reconnect path used after a failed request.
        """
        await self.master.connect()

    async def close(self) -> None:
        """Close the underlying connection, ignoring errors."""
        writer = self.master._sock_writer
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


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
        self._current_temperature: float = None
        self._relay_status: bool = None

    async def init(self) -> None:
        """Perform the initial reads. Devices must already be connected."""
        self._current_temperature = await self._read_current_temperature()
        self._relay_status = await self._read_relay_status()

    async def set_relay_status(self, status: bool) -> bool:
        """Set the relay status and return the value written.

        Raises OSError if the device does not confirm the write.
        """
        success = await self._relay_device.master.write_single_coil(
            slave_addr=self._relay_device.node_id,
            output_address=self._relay_register,
            output_value=status,
        )
        if not success:
            raise OSError("write_single_coil not confirmed by device")
        self._relay_status = status
        return status

    async def _read_relay_status(self) -> bool:
        """Read the current status of the relay."""
        result = await self._relay_device.master.read_coils(
            slave_addr=self._relay_device.node_id,
            starting_addr=self._relay_register,
            coil_qty=1,
        )
        return result[0]

    @property
    def relay_status(self) -> bool:
        """Get the current relay status."""
        return self._relay_status

    async def update_relay_status(self) -> None:
        """Update the relay status."""
        self._relay_status = await self._read_relay_status()

    async def _read_current_temperature(self) -> float:
        """Get the current temperature from the sensor."""
        temperatures = await self._temp_device.master.read_input_registers(
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
        """Build device and room objects from configuration file (no I/O yet).

        Call `connect()` (or use the `create()` factory) before use.
        """
        config = json.load(open(CONFIG_FILE))
        modbus_config = config["devices"]
        self.devices: dict[str, ModbusDevice] = {}
        self.rooms: dict[str, RoomConfig] = {}
        for device_name, device_config in modbus_config.items():
            self.devices[device_name] = ModbusDevice(
                ip=device_config["ip"], port=device_config["port"], node_id=device_config["node_id"]
            )

        for room_name, room_config in config["rooms"].items():
            self.rooms[room_name] = RoomConfig(
                temperature_device=self.devices[room_config["temperature_sensor"]["device"]],
                temperature_register=room_config["temperature_sensor"]["register"],
                relay_device=self.devices[room_config["relay"]["device"]],
                relay_register=room_config["relay"]["register"],
            )

    async def connect(self) -> None:
        """Connect to all configured devices and perform the initial room reads."""
        try:
            for device in self.devices.values():
                await device.connect()

            for room in self.rooms.values():
                await room.init()
        except Exception:
            # If connect() fails partway through (e.g. a later device is
            # unreachable, or a RoomConfig's initial read fails), any devices
            # already connected above are about to become unreferenced along
            # with this half-built ModbusController. Their sockets would
            # otherwise stay open indefinitely: closing a socket's underlying
            # lwIP resources requires an explicit close() call, which
            # gc.collect() alone cannot trigger.
            for device in self.devices.values():
                await device.close()
            raise

    @classmethod
    async def create(cls) -> "ModbusController":
        """Build a ModbusController and connect it to all configured devices."""
        self = cls()
        await self.connect()
        return self


