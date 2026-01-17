import json

import machine
import network
import webrepl
from network import LAN, WLAN

nw_config = json.load(open("config/network.json"))

lan = LAN(
    mdc=machine.Pin(23),
    mdio=machine.Pin(18),
    power=machine.Pin(12),
    phy_type=network.PHY_LAN8720,
    phy_addr=0,
    ref_clk=machine.Pin(17),
    ref_clk_mode=machine.Pin.OUT,
)
lan.active(True)
lan.ipconfig(addr4=nw_config["ipconfig"]["addr4"], gw4=nw_config["ipconfig"]["gw4"])
if not lan.isconnected():
    lan.active(False)
    wlan = WLAN(network.STA_IF)
    wlan.active(True)
    network.ipconfig(dns=nw_config["ipconfig"]["dns"])
    wlan.ipconfig(addr4=nw_config["ipconfig"]["addr4"], gw4=nw_config["ipconfig"]["gw4"])
    if not wlan.isconnected():
        print("connecting to network...")
        wlan.connect(nw_config["wifi"]["ssid"], nw_config["wifi"]["password"])
        while not wlan.isconnected():
            pass
    print("network config:", wlan.ifconfig())

webrepl.start(password="1234")
