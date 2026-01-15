import machine
import network
import webrepl

lan = network.LAN(
    mdc=machine.Pin(23),
    mdio=machine.Pin(18),
    power=machine.Pin(12),
    phy_type=network.PHY_LAN8720,
    phy_addr=0,
    ref_clk=machine.Pin(17),
    ref_clk_mode=machine.Pin.OUT,
)
lan.active(True)
lan.ipconfig("addr4")

webrepl.start()
