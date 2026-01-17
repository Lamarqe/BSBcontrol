import time

from umodbus.tcp import TCP as ModbusTCPMaster

temp_host = ModbusTCPMaster(slave_ip="192.168.2.151", slave_port=502)
relay_host = ModbusTCPMaster(slave_ip="192.168.2.153", slave_port=502)

# address of the target/client/slave device on the bus
temp_slave_addr = 1
temp_register_id = 0
temp_qty = 1

temperatures = temp_host.read_input_registers(
    slave_addr=temp_slave_addr,
    starting_addr=temp_register_id,
    register_qty=temp_qty,
    signed=False,
)
for temperature in temperatures:
    temperature_celsius = temperature / 10.0
    print("Temperature {}: {:.1f} °C".format(temp_register_id, temperature_celsius))
    temp_register_id += 1

relay_slave_addr = 1
relay_register_id = 0
relay_qty = 1
relay_host.write_single_coil(
    slave_addr=relay_slave_addr,
    output_address=relay_register_id,
    output_value=False,
)
print("Relay {} turned Off".format(relay_register_id + 1))
time.sleep(1)

relay_status = relay_host.read_coils(
    slave_addr=relay_slave_addr,
    starting_addr=relay_register_id,
    coil_qty=relay_qty,
)
for status in relay_status:
    print("Relay {} status: {}".format(relay_register_id + 1, "On" if status else "Off"))
    relay_register_id += 1

relay_register_id = 0
relay_host.write_single_coil(
    slave_addr=relay_slave_addr,
    output_address=relay_register_id,
    output_value=True,
)
print("Relay {} turned On".format(relay_register_id + 1))
time.sleep(1)

relay_status = relay_host.read_coils(
    slave_addr=relay_slave_addr,
    starting_addr=relay_register_id,
    coil_qty=1,
)
for status in relay_status:
    print("Relay {} status: {}".format(relay_register_id + 1, "On" if status else "Off"))
