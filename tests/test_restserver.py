import asyncio
import re

import pytest

from restserver import RestServer


class FakeRoom:
    def __init__(self, current_temperature, target_temperature=22.0, relay_on=False):
        self.current_temperature = current_temperature
        self.target_temperature = target_temperature
        self.relay_on = relay_on


class FakeThermostat:
    rooms = {
        "Arbeitszimmer": FakeRoom(21.4),
        "Schlafzimmer": FakeRoom(19.8),
        "Kueche": FakeRoom(20.1),
    }

    def set_target_temperature(self, room_name, target_temperature):
        self.rooms[room_name].target_temperature = target_temperature


class FakeRequest:
    def __init__(self, json):
        self.json = json


def target_temperature_post_handler(server):
    for methods, pattern, handler, _, _ in server.app.url_map:
        if methods == ["POST"] and pattern.url_pattern == "/target_temperature/update":
            return handler
    raise AssertionError("target temperature update route not registered")


def test_matching_rooms_matches_room_regexp():
    server = RestServer(FakeThermostat(), None)

    matching_rooms = server.matching_rooms(".*zimmer")

    assert set(matching_rooms) == {"Arbeitszimmer", "Schlafzimmer"}
    assert matching_rooms["Arbeitszimmer"].current_temperature == 21.4
    assert matching_rooms["Schlafzimmer"].current_temperature == 19.8


def test_matching_rooms_raises_for_invalid_regexp():
    server = RestServer(FakeThermostat(), None)

    with pytest.raises((re.error, ValueError, TypeError)):
        server.matching_rooms("[")


def test_resolve_rooms_returns_matching_rooms_without_error():
    server = RestServer(FakeThermostat(), None)

    matching_rooms, error = server.resolve_rooms(".*zimmer")

    assert set(matching_rooms) == {"Arbeitszimmer", "Schlafzimmer"}
    assert error is None


@pytest.mark.parametrize(
    ("thermostat", "room_regexp", "expected"),
    [
        (None, ".*", ({"message": "thermostat not ready"}, 503)),
        (FakeThermostat(), "[", ({"message": "invalid room regexp"}, 400)),
        (FakeThermostat(), "unknown", ({"message": "no such room"}, 404)),
    ],
)
def test_resolve_rooms_centralizes_errors(thermostat, room_regexp, expected):
    server = RestServer(thermostat, None)

    matching_rooms, error = server.resolve_rooms(room_regexp)

    assert matching_rooms is None
    assert error == expected


def test_target_temperature_update_uses_literal_rooms():
    thermostat = FakeThermostat()
    server = RestServer(thermostat, None)
    handler = target_temperature_post_handler(server)

    response = asyncio.run(
        handler(FakeRequest({"target_temperature": {"Arbeitszimmer": 21.5, "Schlafzimmer": 19.0}}))
    )

    assert response == {"message": "updated"}
    assert thermostat.rooms["Arbeitszimmer"].target_temperature == 21.5
    assert thermostat.rooms["Schlafzimmer"].target_temperature == 19.0


def test_target_temperature_update_rejects_regexp_room_key():
    thermostat = FakeThermostat()
    server = RestServer(thermostat, None)
    handler = target_temperature_post_handler(server)

    response = asyncio.run(handler(FakeRequest({"target_temperature": {".*zimmer": 21.5}})))

    assert response == ({"message": "no such room: .*zimmer"}, 404)


@pytest.mark.parametrize("target_temperature", ["21.5", True, None, [21.5]])
def test_target_temperature_update_rejects_unsupported_value_types(target_temperature):
    thermostat = FakeThermostat()
    server = RestServer(thermostat, None)
    handler = target_temperature_post_handler(server)
    previous_temperature = thermostat.rooms["Arbeitszimmer"].target_temperature

    response = asyncio.run(
        handler(FakeRequest({"target_temperature": {"Arbeitszimmer": target_temperature}}))
    )

    assert response == ({"message": "invalid target temperatures"}, 400)
    assert thermostat.rooms["Arbeitszimmer"].target_temperature == previous_temperature