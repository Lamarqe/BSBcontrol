#!/usr/bin/env python3
"""Update target temperatures for one or more rooms via the REST API."""

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "/target_temperature/update"
DEVICE = "192.168.2.150"
TARGET_TEMPERATURES = {
    "Wohnzimmer": 21.5,
    "Kueche": 20.5,
    "FlurEG": 21.0,
    "Arbeit": 19.0,
    "Gaeste": 18.0,
    "FlurKG": 17.0,
    "WC": 21.0,
}


def update_target_temperatures(device, room_temperatures):
    if not device.startswith(("http://", "https://")):
        device = "http://" + device
    url = device.rstrip("/") + ENDPOINT
    payload = json.dumps({"target_temperature": dict(room_temperatures)}).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def main():
    try:
        response = update_target_temperatures(DEVICE, TARGET_TEMPERATURES.items())
    except (HTTPError, URLError) as error:
        print("REST request failed: {}".format(error), file=sys.stderr)
        return 1

    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
