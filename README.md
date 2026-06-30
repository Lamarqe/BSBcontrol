# BSBcontrol

MicroPython thermostat controller running on an Olimex ESP32-POE. Reads room
temperatures and drives heating relays via Modbus TCP, communicates with a BSB
boiler (Brötje / Elco / ...) over the BSB bus, and exposes everything through
a REST API.

## REST API

The device listens on port 80. Room names are configured in `config/modbus.json`;
BSB field IDs are configured in `config/bsb.json`.

Replace `192.168.2.150` with the device's actual IP address.

---

### Index

```
GET /
```

Returns a plain HTML welcome page. Useful as a connectivity check.

```bash
curl http://192.168.2.150/
```

---

### Room temperature (current)

```
GET /current_temperature/<room>
```

Returns the temperature currently measured by the Modbus sensor for the given room.

```bash
curl http://192.168.2.150/current_temperature/Arbeitszimmer
```

```json
{"current_temperature": 21.4}
```

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| 404 | `{"message": "no such room"}` | Room name not in `config/modbus.json` |

---

### Room temperature (target) — read

```
GET /target_temperature/<room>
```

Returns the current target (setpoint) temperature for the given room.

```bash
curl http://192.168.2.150/target_temperature/Arbeitszimmer
```

```json
{"target_temperature": 22.0}
```

---

### Room temperature (target) — write

```
POST /target_temperature/<room>
Content-Type: application/json
```

Updates the heating setpoint for the given room. The relay hysteresis is ±0.5 °C.

```bash
curl -X POST http://192.168.2.150/target_temperature/Arbeitszimmer \
     -H "Content-Type: application/json" \
     -d '{"target_temperature": 21.5}'
```

```json
{"message": "updated"}
```

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| 404 | `{"message": "no such room"}` | Room name not in `config/modbus.json` |

---

### BSB field — read

```
GET /bsb/field/<id>
```

Sends a GET telegram to the boiler and returns the decoded value. Field IDs
must be listed in `config/bsb.json`. The request blocks until the boiler
responds (typically < 1 s) or a 5 s timeout expires.

**Configured fields**

| ID | Name | Unit | Writable |
|----|------|------|----------|
| 700 | Operating mode (`Betriebsart`) | — | yes |
| 710 | Comfort setpoint (`Komfortsollwert`) | °C | yes |
| 8700 | Outside temperature (`Aussentemperatur`) | °C | no |
| 8743 | Flow temperature (`Vorlauftemperatur`) | °C | no |

```bash
# Outside temperature
curl http://192.168.2.150/bsb/field/8700
```

```json
{"id": 8700, "name": "Aussentemperatur", "value": 14.3, "unit": "°C"}
```

```bash
# Operating mode (enum)
curl http://192.168.2.150/bsb/field/700
```

```json
{"id": 700, "name": "Betriebsart", "value": 1, "unit": ""}
```

Enum values for field 700: `0` = Schutzbetrieb, `1` = Automatik, `2` = Reduziert, `3` = Komfort.

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| 404 | `{"message": "unknown field"}` | ID not in `config/bsb.json` |
| 504 | `{"message": "timeout"}` | Boiler did not respond within 5 s |

---

### BSB field — write

```
POST /bsb/field/<id>
Content-Type: application/json
```

Sends a SET telegram to the boiler. Only fields that are not read-only can be written.

```bash
# Switch to Automatik mode
curl -X POST http://192.168.2.150/bsb/field/700 \
     -H "Content-Type: application/json" \
     -d '{"value": 1}'
```

```bash
# Set comfort setpoint to 21 °C
curl -X POST http://192.168.2.150/bsb/field/710 \
     -H "Content-Type: application/json" \
     -d '{"value": 21.0}'
```

```json
{"message": "updated"}
```

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| 404 | `{"message": "unknown field"}` or `{"message": "..."}` | ID not in `config/bsb.json` or field is read-only |
| 504 | `{"message": "timeout"}` | Boiler did not respond within 5 s |

---

## Configuration files

| File | Purpose |
|------|---------|
| `config/network.json` | Static IP, gateway, Wi-Fi fallback credentials |
| `config/modbus.json` | Modbus device IPs and room → sensor/relay mapping |
| `config/bsb.json` | BSB own address, destination address, whitelisted field IDs |
| `config/bsb_device.json` | Trimmed boiler device model (auto-generated, do not edit) |
| `config/bsb_types.json` | Trimmed BSB type definitions (auto-generated, do not edit) |

## Adding BSB fields

1. Add the numeric field ID to the `"fields"` list in `config/bsb.json`.
2. Re-run the extraction script on the dev machine to regenerate `config/bsb_device.json` and `config/bsb_types.json`.
3. Deploy the updated config files to the device.

## Components

- Modbus:
  - read room temperatures
  - control heating relays
- BSB boiler bus:
  - read outside / flow temperatures
  - read and write heating operating mode and setpoints
- REST API server:
  - change target room temperature
  - read/write BSB field values

---

## Target functionality (to be added in future versions)

Components planned but not yet implemented:

- BSBgateway integration:
  - control heating & water schedules based on:
    - energy prices
    - solar production forecast
    - outside temperature (heat pump COP)
- REST client — communicate with Home Assistant API:
  - read energy prices
  - read solar production forecast (sun duration, from weather)
  - read solar production (?)
- REST API server extensions:
  - external access to all kind of values (template number entity)

Triggers planned:

- Timeouts:
  - re-calculate heating relay status (10 seconds?)
    - re-read room temperatures
  - re-calculate heating and water schedules (6 hours?)
- API callbacks:
  - update of target room temperature
