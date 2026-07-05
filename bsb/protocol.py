# SPDX-License-Identifier: LGPL-3.0-or-later
# BSB bus protocol layer - MicroPython port

import struct
import time

DEBUG = False

# ---------------------------------------------------------------------------
# CRC16-XMODEM
# ---------------------------------------------------------------------------

CRC16_XMODEM_TABLE = [
        0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
        0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef,
        0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
        0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de,
        0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485,
        0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
        0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4,
        0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc,
        0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
        0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b,
        0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12,
        0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
        0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41,
        0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49,
        0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
        0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59, 0x8f78,
        0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f,
        0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
        0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e,
        0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256,
        0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
        0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
        0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c,
        0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
        0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab,
        0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3,
        0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
        0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92,
        0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9,
        0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
        0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8,
        0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0,
        ]


def _crc16(data, crc, table):
    for byte in data:
        crc = ((crc << 8) & 0xff00) ^ table[((crc >> 8) & 0xff) ^ byte]
    return crc & 0xffff


def crc16xmodem(data, crc=0):
    return _crc16(data, crc, CRC16_XMODEM_TABLE)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class BsbError(Exception):
    pass

class EncodeError(BsbError):
    pass

class DecodeError(Exception):
    pass

class ValidateError(BsbError):
    pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class BsbDatatype:
    Vals = "VALS"
    Enum = "ENUM"
    Bits = "BITS"
    String = "STRN"
    Datetime = "DTTM"
    DayMonth = "DDMM"
    Time = "THMS"
    HourMinutes = "HHMM"
    TimeProgram = "TMPR"
    Date = "DWHM"
    Raw = "RAW"


class BsbCommandFlags:
    Readonly  = 0x01
    Writeonly = 0x02
    OEM       = 0x04
    NoCmd     = 0x08
    SpecialInf = 0x10
    EEPROM    = 0x20
    SWCtlRonly = 0x40


class BsbType:
    def __init__(self, name, datatype, payload_length, factor=1, unsigned=False, unit="", enable_byte=0):
        self.name = name
        self.datatype = datatype
        self.payload_length = payload_length
        self.factor = factor
        self.unsigned = unsigned
        self.unit = unit
        self.enable_byte = enable_byte

    @property
    def nullable(self):
        return self.enable_byte == 6

    @classmethod
    def raw(cls):
        return cls(name="RAW", datatype=BsbDatatype.Raw, payload_length=0)


class BsbCommand:
    def __init__(self, parameter, telegram_id, disp_name="", bsb_type=None,
                 unit="", enum=None, min_value=None, max_value=None, flags=0):
        self.parameter = parameter
        self.telegram_id = telegram_id
        self.disp_name = disp_name
        self.bsb_type = bsb_type
        self.unit = unit
        self.enum = enum
        self.min_value = min_value
        self.max_value = max_value
        self.flags = flags

    @classmethod
    def unknown(cls, telegram_id):
        return cls(
            parameter=0,
            telegram_id=telegram_id,
            disp_name="unknown command",
            bsb_type=BsbType.raw(),
        )


# ---------------------------------------------------------------------------
# Payload decode
# ---------------------------------------------------------------------------
# Flag byte semantics  (authoritative source: BSB-LAN defs.h + old bsbgateway)
#
# All VALS/ENUM/BITS/Datetime types carry a leading flag byte on the wire.
# TimeProgram and String do NOT — their payload_length+1 bytes are fully used
# for data (12 slot bytes / null-terminated string).
#
# enable_byte (from bsb-types.json, mirrors BSB-LAN's optbl):
#   0 or 1  ->  non-nullable type.  "value present" flag for SET = 0x01.
#   6       ->  nullable type.      "value present" flag for SET = 0x06.
#   8       ->  TimeProgram / no flag byte.
#
# RET packet (heating controller → us):
#   Non-nullable: flag byte present but NOT used for null detection.
#                 Always strip and decode regardless of flag value.
#                 (Some controllers send flag=0x00, others send flag=0x01.)
#   Nullable:     flag == enable_byte (0x06) → value present, strip and decode.
#                 flag != enable_byte         → null/unavailable, return None.
#
# SET packet (us → heating controller):
#   Non-nullable: flag = enable_byte (0x01) for value present.
#   Nullable:     flag = enable_byte (0x06) for value present.
#   Nullable null:flag = 0x05 to request "disable".
#
# Encoding RET (used only in tests / simulator context, not on the wire):
#   Non-nullable non-null: flag = 0x00
#   Nullable non-null:     flag = enable_byte (0x06)
#   Nullable null:         flag = 0x01  (what a real controller sends)
# ---------------------------------------------------------------------------

def _is_null_flag(bsb_type, flag, packettype):
    """Return True when the flag byte signals that no value is available.

    Only nullable types (enable_byte == 6) can signal null:
      "ret": flag != enable_byte (e.g. flag == 0x01 from controller means null)
      "set": flag == 0x05 (client requests controller to disable the field)
    Non-nullable types never signal null via the flag byte.
    """
    if not bsb_type.nullable:
        return False
    if packettype == "ret":
        return flag != bsb_type.enable_byte   # anything other than 0x06 = null
    else:
        return flag == 0x05                   # set: explicit disable request


def decode(data, bsb_type, packettype="ret"):
    if bsb_type.datatype == BsbDatatype.Raw:
        return data

    # Wire payload is always payload_length + 1 bytes for all types (capped at 22).
    # For VALS/ENUM/BITS/Datetime: the +1 is the flag byte.
    # For TimeProgram: payload_length=11 + 1 = 12 actual slot bytes (no flag byte).
    # For String: the +1 is the null terminator (no flag byte).
    expected_len = min(bsb_type.payload_length + 1, 22)
    if len(data) != expected_len:
        raise DecodeError(
            "Payload has wrong length. Expected %d bytes, got %d"
            % (expected_len, len(data))
        )

    if bsb_type.datatype not in (BsbDatatype.TimeProgram, BsbDatatype.String, BsbDatatype.Raw):
        flag = data[0]
        if _is_null_flag(bsb_type, flag, packettype):
            return None
        data = data[1:]
    if bsb_type.name == "YEAR":
        return _decode_dt(data, bsb_type)
    elif bsb_type.datatype == BsbDatatype.Vals:
        return _decode_vals(data, bsb_type)
    elif bsb_type.datatype == BsbDatatype.Enum:
        return _decode_enum(data, bsb_type)
    elif bsb_type.datatype == BsbDatatype.Bits:
        return data
    elif bsb_type.datatype in (BsbDatatype.Datetime, BsbDatatype.DayMonth, BsbDatatype.Time):
        return _decode_dt(data, bsb_type)
    elif bsb_type.datatype == BsbDatatype.HourMinutes:
        return _decode_hourminute(data)
    elif bsb_type.datatype == BsbDatatype.TimeProgram:
        return _decode_timeprogram(data)
    elif bsb_type.datatype == BsbDatatype.String:
        return _decode_string(data)
    else:
        return data


def _decode_vals(data, bsb_type):
    assert bsb_type.payload_length in [1, 2, 4]
    code = {1: "b", 2: "h", 4: "i"}[bsb_type.payload_length]
    if bsb_type.unsigned or bsb_type.datatype != BsbDatatype.Vals:
        code = code.upper()
    (intval,) = struct.unpack(">" + code, data)
    if bsb_type.factor == 1:
        return intval
    else:
        return float(intval) / bsb_type.factor


def _decode_enum(data, bsb_type):
    assert bsb_type.payload_length == 1
    assert len(data) == 1
    (val,) = struct.unpack("B", data)
    return val


def _decode_dt(data, bsb_type):
    """Decode 8-byte date/time payload (flag byte already stripped).

    Returns MicroPython-compatible tuples instead of datetime objects:
    - YEAR name       -> int (year)
    - VACATIONPROG    -> (month, day)
    - Datetime        -> (year, month, day, hour, minute, second)
    - DayMonth        -> (month, day)
    - Time            -> (hour, minute, second)
    """
    year, month, day, dow, hour, minute, second, flag = struct.unpack("8B", data)
    year = year + 1900
    if bsb_type.name == "YEAR":
        if flag != 0x0F:
            raise DecodeError("YEAR field: expected flag 0x0F, got 0x%02x" % flag)
        return year
    elif bsb_type.name == "VACATIONPROG":
        if flag != 0x17:
            raise DecodeError("VACATIONPROG field: expected flag 0x17, got 0x%02x" % flag)
        return (month, day)
    elif bsb_type.datatype == BsbDatatype.Datetime:
        if flag != 0x00:
            raise DecodeError("Datetime field: expected flag 0x00, got 0x%02x" % flag)
        return (year, month, day, hour, minute, second)
    elif bsb_type.datatype == BsbDatatype.DayMonth:
        if flag != 0x16:
            raise DecodeError("DayMonth field: expected flag 0x16, got 0x%02x" % flag)
        return (month, day)
    elif bsb_type.datatype == BsbDatatype.Time:
        if flag != 0x1D:
            raise DecodeError("Time field: expected flag 0x1D, got 0x%02x" % flag)
        return (hour, minute, second)
    else:
        raise DecodeError("Cannot decode datetime field of type %s" % bsb_type.datatype)


def _decode_hourminute(data):
    """Decode 2-byte HH:MM payload -> (hour, minute) tuple."""
    h, m = struct.unpack("2B", data)
    return (h, m)


def _decode_string(data):
    """Decode null-padded bytes -> str (latin-1)."""
    if b"\x00" in data:
        data = data[:data.index(b"\x00")]
    return data.decode("latin-1")


def _decode_timeprogram(data):
    """Decode 12-byte time program -> list of ((h1,m1),(h2,m2)) tuples."""
    assert len(data) == 12
    result = []
    for ofs in (0, 4, 8):
        if data[ofs] & 0x80:
            continue
        h1, m1, h2, m2 = struct.unpack("4B", data[ofs:ofs + 4])
        result.append(((h1, m1), (h2, m2)))
    return result


# ---------------------------------------------------------------------------
# Payload encode
# ---------------------------------------------------------------------------

def encode(data, bsb_type, command, validate=True, packettype="set"):
    if validate:
        if command.flags & BsbCommandFlags.Readonly:
            raise ValidateError("Command is read-only")
        if command.enum and data is not None:
            if data not in command.enum:
                raise ValidateError(
                    "Value %s not in enum values: %s" % (data, list(command.enum.keys()))
                )
        if isinstance(data, (int, float)) and data is not None:
            if command.min_value is not None and data < command.min_value:
                raise ValidateError(
                    "Value %s is below minimum %s" % (data, command.min_value)
                )
            if command.max_value is not None and data > command.max_value:
                raise ValidateError(
                    "Value %s is above maximum %s" % (data, command.max_value)
                )

    if bsb_type.datatype == BsbDatatype.Raw:
        return bytes(data)

    if data is None:
        if not bsb_type.nullable:
            raise EncodeError("Type is not nullable, cannot encode None")
        if packettype == "ret":
            flag = 0x01              # ret: null value (what a real controller sends)
        else:
            flag = 0x05              # set: request controller to disable
    else:
        if packettype == "ret":
            if bsb_type.nullable:
                flag = bsb_type.enable_byte  # 0x06: nullable type, value present
            else:
                flag = 0x00              # 0x00: non-nullable type, value present
        else:
            flag = bsb_type.enable_byte  # set: always use enable_byte (0x01 or 0x06)

    if data is not None:
        if bsb_type.name == "YEAR":
            payload = _encode_dt(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.Vals:
            payload = _encode_vals(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.Enum:
            payload = _encode_enum(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.Bits:
            payload = bytes(data)
        elif bsb_type.datatype in (BsbDatatype.Datetime, BsbDatatype.DayMonth, BsbDatatype.Time):
            payload = _encode_dt(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.HourMinutes:
            payload = _encode_hourminute(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.TimeProgram:
            payload = _encode_timeprogram(data, bsb_type)
        elif bsb_type.datatype == BsbDatatype.String:
            payload = _encode_string(data, bsb_type)
        else:
            raise EncodeError("No encoder for datatype %s" % bsb_type.datatype)
    else:
        payload = b'\x00' * bsb_type.payload_length

    if bsb_type.datatype not in (BsbDatatype.TimeProgram, BsbDatatype.String, BsbDatatype.Raw):
        return bytes([flag]) + payload
    return payload


def _encode_vals(data, bsb_type):
    if not isinstance(data, (int, float)):
        raise EncodeError("Expected numeric value, got %s" % type(data).__name__)
    if bsb_type.factor != 1:
        intval = int(round(data * bsb_type.factor))
    else:
        intval = int(data)
    assert bsb_type.payload_length in [1, 2, 4]
    code = {1: "b", 2: "h", 4: "i"}[bsb_type.payload_length]
    if bsb_type.unsigned or bsb_type.datatype != BsbDatatype.Vals:
        code = code.upper()
    return struct.pack(">" + code, intval)


def _encode_enum(data, bsb_type):
    if not isinstance(data, int):
        raise EncodeError("Expected int for enum, got %s" % type(data).__name__)
    if data < 0 or data > 255:
        raise EncodeError("Enum value %d out of range [0, 255]" % data)
    assert bsb_type.payload_length == 1
    return struct.pack("B", data)


def _encode_dt(data, bsb_type):
    """Encode date/time tuple to 8-byte BSB payload.

    Input types mirror _decode_dt outputs:
    - YEAR name       : int
    - VACATIONPROG    : (month, day)
    - Datetime        : (year, month, day, hour, minute, second)
    - DayMonth        : (month, day)
    - Time            : (hour, minute, second)
    """
    if bsb_type.name == "YEAR":
        if not isinstance(data, int):
            raise EncodeError("YEAR expects int, got %s" % type(data).__name__)
        return struct.pack("8B", data - 1900, 0, 0, 0, 0, 0, 0, 0x0F)
    elif bsb_type.name == "VACATIONPROG":
        month, day = data
        return struct.pack("8B", 0, month, day, 0, 0, 0, 0, 0x17)
    elif bsb_type.datatype == BsbDatatype.Datetime:
        year, month, day, hour, minute, second = data
        return struct.pack("8B", year - 1900, month, day, 0, hour, minute, second, 0x00)
    elif bsb_type.datatype == BsbDatatype.DayMonth:
        month, day = data
        return struct.pack("8B", 0, month, day, 0, 0, 0, 0, 0x16)
    elif bsb_type.datatype == BsbDatatype.Time:
        hour, minute, second = data
        return struct.pack("8B", 0, 0, 0, 0, hour, minute, second, 0x1D)
    else:
        raise EncodeError("Cannot encode datetime field of type %s" % bsb_type.datatype)


def _encode_hourminute(data, bsb_type):
    """Encode (hour, minute) tuple to 2 bytes."""
    hour, minute = data
    return struct.pack("2B", hour, minute)


def _encode_string(data, bsb_type):
    """Encode str to null-padded bytes (latin-1)."""
    if not isinstance(data, str):
        raise EncodeError("Expected str, got %s" % type(data).__name__)
    encoded = data.encode("latin-1")
    expected_len = min(bsb_type.payload_length + 1, 22)
    if len(encoded) > bsb_type.payload_length:
        raise EncodeError("String too long: %d > %d" % (len(encoded), bsb_type.payload_length))
    return encoded + b'\x00' * (expected_len - len(encoded))


def _encode_timeprogram(data, bsb_type):
    """Encode list of ((h1,m1),(h2,m2)) tuples to 12-byte time program."""
    if len(data) > 3:
        raise EncodeError("TimeProgram supports at most 3 entries, got %d" % len(data))
    result = b""
    for entry in data:
        (h1, m1), (h2, m2) = entry
        result += struct.pack("4B", h1, m1, h2, m2)
    while len(result) < 12:
        result += b'\x80\x00\x00\x00'
    return result


# ---------------------------------------------------------------------------
# Bus-level byte inversion helper
# ---------------------------------------------------------------------------

def invert(data):
    return bytes(b ^ 0xFF for b in data)


# ---------------------------------------------------------------------------
# BSB Telegram
# ---------------------------------------------------------------------------

_PACKETTYPES = {
    2: "inf",
    3: "set",
    4: "ack",
    6: "get",
    7: "ret",
}

_PACKETTYPES_R = {value: key for key, value in _PACKETTYPES.items()}


class BsbTelegram:
    def __init__(self, command, src=0, dst=0, packettype="get",
                 rawdata=b"", data=None, timestamp=0):
        self.command = command
        self.src = src
        self.dst = dst
        self.packettype = packettype
        self.rawdata = rawdata
        self.data = data
        self.timestamp = timestamp

    @property
    def field(o):
        return o.command

    @classmethod
    def deserialize(cls, data, device):
        indata = data
        assert isinstance(indata, bytes)
        result = []
        while indata:
            try:
                t, indata = cls._parse(indata, device)
                result.append(t)
            except DecodeError as e:
                junk, indata = cls._skip(indata)
                result.append((junk, e.args[0]))
        return result

    @classmethod
    def _skip(cls, data):
        try:
            idx = data.index(b'\xdc', 1)
        except ValueError:
            return data, b""
        return data[:idx], data[idx:]

    @classmethod
    def _validate(cls, data):
        if data[0] != 0xDC:
            raise DecodeError("bad start marker")
        if len(data) < 11 or len(data) < data[3]:
            raise DecodeError("incomplete telegram")
        if data[4] not in _PACKETTYPES:
            raise DecodeError("unknown packet type: %d" % data[4])
        tlen = data[3]
        if tlen < 11:
            raise DecodeError("bad length: telegram cannot be shorter than 11 bytes")
        crc = crc16xmodem(data[:tlen])
        if crc != 0:
            pretty = "".join("%0.2X " % i for i in data[:tlen])
            raise DecodeError("bad crc checksum for: " + pretty)

    @classmethod
    def _parse(cls, data, device):
        cls._validate(data)

        src = data[1] ^ 0x80
        dst = data[2]
        dlen = data[3]
        packettype = _PACKETTYPES[data[4]]

        fidbytes = [data[i] for i in (5, 6, 7, 8)]
        if packettype in ["get", "set"]:
            fidbytes[0], fidbytes[1] = fidbytes[1], fidbytes[0]

        fieldid = 0
        mult = 0x1000000
        for d in fidbytes:
            fieldid = d * mult + fieldid
            mult = mult // 0x100

        field = BsbCommand.unknown(fieldid)
        if device is not None:
            field = device.get(fieldid, field)

        rawdata = data[9:dlen - 2]
        if rawdata and field.bsb_type:
            value = decode(rawdata, field.bsb_type, packettype=packettype)
        else:
            value = None
        if DEBUG:
            print("[BSB] parse: type=%s tid=0x%08X known=%s raw=%s value=%r" % (
                packettype,
                fieldid,
                field.bsb_type is not None,
                " ".join("%02X" % b for b in rawdata),
                value,
            ))

        t = cls(
            command=field,
            src=src,
            dst=dst,
            packettype=packettype,
            rawdata=rawdata,
            data=value,
        )
        return t, data[dlen:]

    def serialize(o, validate=True):
        result = [
            0xDC,
            o.src ^ 0x80,
            o.dst,
            0,
            _PACKETTYPES_R[o.packettype],
        ]
        tid = o.command.telegram_id
        id_bytes = [
            (tid & 0xFF000000) >> 24,
            (tid & 0xFF0000) >> 16,
            (tid & 0xFF00) >> 8,
            tid & 0xFF,
        ]
        if o.packettype in ["get", "set"]:
            id_bytes[1], id_bytes[0] = id_bytes[0], id_bytes[1]
        result += id_bytes

        if o.packettype == "ret" or o.packettype == "set":
            assert o.command.bsb_type is not None, "Cannot serialize telegram without type information"
            result += list(
                encode(o.data, o.command.bsb_type, o.command, validate=validate, packettype=o.packettype)
            )

        result[3] = len(result) + 2

        crc = crc16xmodem(result)
        result.append((crc & 0xFF00) >> 8)
        result.append(crc & 0xFF)
        return bytes(result)

    def __str__(o):
        rawdata = "".join(["%0.2X " % i for i in o.rawdata])
        if o.timestamp:
            t = time.localtime(int(o.timestamp))
            ts = " @%02d:%02d:%02d" % (t[3], t[4], t[5])
        else:
            ts = ""
        unit = o.field.unit
        unit = " " + unit if unit else ""
        if o.field.parameter > 0:
            fieldname = "%d %s" % (o.field.parameter, o.field.disp_name)
        else:
            fieldname = "%s 0x%08X" % (o.field.disp_name, o.field.telegram_id)

        if o.packettype in ("ret", "set", "inf"):
            data_txt = " = %s%s [raw:%s]" % (o.data, unit, rawdata)
        else:
            data_txt = ""

        return "<BsbTelegram %d -> %d: %s %s%s%s>" % (
            o.src, o.dst, o.packettype, fieldname, data_txt, ts
        )
