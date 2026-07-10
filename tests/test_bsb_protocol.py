# Tests for bsb_protocol.py — translated from bsbgateway/tests/test_payload_decode.py
# and test_payload_encode.py. Key adaptations vs. the original:
#   - BsbType built with plain __init__ (no attrs/evolve)
#   - datetime/date/time objects replaced with tuples: (y,m,d,h,m,s), (m,d), (h,m,s), (h,m)
#   - ScheduleEntry((on, off)) replaced with ((h1,m1),(h2,m2)) tuples
#   - Bits encode is supported here (not EncodeError as in bsbgateway)

import pytest
from bsb.protocol import (
    BsbType, BsbDatatype, BsbCommand, BsbCommandFlags, BsbTelegram,
    decode, encode, crc16xmodem, invert,
    DecodeError, EncodeError, ValidateError,
)


# ---------------------------------------------------------------------------
# Shared type fixtures
# ---------------------------------------------------------------------------

def _t(dt, pl, factor=1, unsigned=False, enable_byte=1, name="test"):
    return BsbType(name=name, datatype=dt, payload_length=pl,
                   factor=factor, unsigned=unsigned, unit="", enable_byte=enable_byte)


int8          = _t(BsbDatatype.Vals, 1)
uint8         = _t(BsbDatatype.Vals, 1, unsigned=True)
int16         = _t(BsbDatatype.Vals, 2)
uint16        = _t(BsbDatatype.Vals, 2, unsigned=True)
int32         = _t(BsbDatatype.Vals, 4)
int40         = _t(BsbDatatype.Vals, 5)          # payload_length=5 is invalid → AssertionError
int16_10      = _t(BsbDatatype.Vals, 2, factor=10)
bits          = _t(BsbDatatype.Bits, 1)
enum          = _t(BsbDatatype.Enum, 1)
year          = BsbType(name="YEAR", datatype=BsbDatatype.Vals, payload_length=8, enable_byte=1, unit="")
dttm          = _t(BsbDatatype.Datetime, 8)
ddmm          = _t(BsbDatatype.DayMonth, 8)
ddmm_v        = _t(BsbDatatype.DayMonth, 8, name="VACATIONPROG")
thms          = _t(BsbDatatype.Time, 8)
hhmm          = _t(BsbDatatype.HourMinutes, 2)
str5          = _t(BsbDatatype.String, 5)
str22         = _t(BsbDatatype.String, 22)
tmpr          = _t(BsbDatatype.TimeProgram, 11, enable_byte=8)
int8_nullable = _t(BsbDatatype.Vals, 1, enable_byte=6)

# 1985-10-26 (Sat) 01:21:01 as wire bytes (including outer flag byte 0x00 for "value present")
# Structure after flag strip: year_offset(85) month(10) day(26) dow(6) hour(1) min(21) sec(1)
# Written as hex: 55 0A 1A 06 01 15 01
# With outer flag: 00 55 0A 1A 06 01 15 01  → _DTVAL (8 bytes); subtype flag appended in test cases
_DTVAL = "00550A1A06011501"


def _h(s):
    """Hex string (with optional spaces) → bytes."""
    return bytes.fromhex(s.replace(" ", ""))


def _SE(h1, m1, h2, m2):
    """Convenience for TimeProgram schedule entry tuple."""
    return ((h1, m1), (h2, m2))


def _cmd(**kwargs):
    defaults = dict(parameter=1, telegram_id=0x12345678)
    defaults.update(kwargs)
    return BsbCommand(**defaults)


# ---------------------------------------------------------------------------
# CRC16 tests
# ---------------------------------------------------------------------------

def test_crc16_empty():
    assert crc16xmodem(b"") == 0x0000


def test_crc16_known_vector():
    # Standard CRC16-XMODEM test vector
    assert crc16xmodem(b"123456789") == 0x31C3


def test_crc16_telegram_self_check():
    # A correctly serialized GET telegram appends its own CRC; feeding the full
    # frame (including those 2 bytes) back into crc16xmodem must give 0.
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = t.serialize()
    assert crc16xmodem(raw) == 0


# ---------------------------------------------------------------------------
# invert helper
# ---------------------------------------------------------------------------

def test_invert_roundtrip():
    data = bytes(range(256))
    assert invert(invert(data)) == data
    assert all(b ^ 0xFF == ib for b, ib in zip(data, invert(data)))


# ---------------------------------------------------------------------------
# decode() — parametrized from bsbgateway test_payload_decode.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data, bsb_type, expect", [
    # ---- Vals ----
    ("000A",           int8,   10),
    ("00ff",           int8,   -1),
    ("00ff",           uint8,  255),
    ("000102",         int16,  258),
    ("00ffff",         int16,  -1),
    ("00ffff",         uint16, 65535),
    ("000104",         int16_10, 26.0),
    ("0000010000",     int32,  65536),
    ("000001",         int32,  DecodeError),      # wrong length (3 != 5)
    ("000001000000",   int40,  AssertionError),   # payload_length=5 not in [1,2,4]
    # ---- Non-nullable: flag byte always stripped, value always decoded ----
    ("010A",           int8,   10),   # flag=0x01 stripped → 0x0A = 10
    ("020A",           int8,   10),   # flag=0x02 stripped → 0x0A = 10
    ("050A",           int8,   10),   # flag=0x05 stripped → 0x0A = 10
    ("060A",           int8,   10),   # flag=0x06 stripped (int8 not nullable) → 10
    # ---- Nullable (enable_byte==6): flag==6 means "value present", flag!=6 means null ----
    ("060A",           int8_nullable, 10),   # flag=0x06 == enable_byte → value present, decode
    ("010A",           int8_nullable, None), # flag=0x01 != enable_byte → null
    # ---- Bits / Enum ----
    ("00FE",           bits,   b"\xFE"),
    ("00FE",           enum,   254),
    # ---- YEAR (name override of Vals) ----
    ("000102",         year,   DecodeError),           # wrong length (3 != 9)
    (_DTVAL + "0F",   year,   1985),
    (_DTVAL + "21",   year,   DecodeError),            # wrong subtype flag
    # ---- Datetime ----
    (_DTVAL + "00",   dttm,   (1985, 10, 26, 1, 21, 1)),
    (_DTVAL + "01",   dttm,   DecodeError),
    # ---- DayMonth ----
    (_DTVAL + "16",   ddmm,   (10, 26)),
    (_DTVAL + "17",   ddmm,   DecodeError),
    (_DTVAL + "17",   ddmm_v, (10, 26)),              # VACATIONPROG uses flag 0x17
    (_DTVAL + "16",   ddmm_v, DecodeError),
    # ---- Time ----
    (_DTVAL + "1d",   thms,   (1, 21, 1)),
    (_DTVAL + "1e",   thms,   DecodeError),
    # ---- HourMinutes ----
    ("000115",         hhmm,   (1, 21)),
    # ---- String ----
    ("65 66 67 00 00 00", str5,  "efg"),
    ("65 66 67 00 00",    str5,  DecodeError),         # 5 bytes, expected 6
    ("65 66 67" + "00" * 18, str22, DecodeError),      # 21 bytes, expected 22
    ("65 66 67" + "00" * 19, str22, "efg"),             # 22 bytes ✓
    ("65 66 67" + "00" * 20, str22, DecodeError),      # 23 bytes, expected 22
    # ---- TimeProgram ----
    ("8000 0000 8000 0000 8000 0000", tmpr, []),
    ("0102 0304 8000 0000 8000 0000", tmpr, [_SE(1,2,3,4)]),
    ("0102 0304 0203 0405 8000 0000", tmpr, [_SE(1,2,3,4), _SE(2,3,4,5)]),
    ("0102 0304 8000 8000 0203 0405", tmpr, [_SE(1,2,3,4), _SE(2,3,4,5)]),  # disabled slot skipped
    ("0102 0304 0100 0300 0203 0405", tmpr, [_SE(1,2,3,4), _SE(1,0,3,0), _SE(2,3,4,5)]),
])
def test_decode(data, bsb_type, expect):
    raw = _h(data)
    if isinstance(expect, type) and issubclass(expect, Exception):
        with pytest.raises(expect):
            decode(raw, bsb_type, packettype="ret")
    else:
        got = decode(raw, bsb_type, packettype="ret")
        assert got == expect
        assert type(got) is type(expect)


# ---------------------------------------------------------------------------
# encode()/decode() roundtrip — adapted from bsbgateway test_payload_encode.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, bsb_type", [
    (10,    int8),
    (-1,    int8),
    (255,   uint8),
    (258,   int16),
    (-1,    int16),
    (65535, uint16),
    (26.0,  int16_10),
    (65536, int32),
    (254,   enum),
    (1985,  year),
    ((1985, 10, 26, 1, 21, 1), dttm),
    ((10, 26), ddmm),
    ((10, 26), ddmm_v),
    ((1, 21, 1), thms),
    ((1, 21),   hhmm),
    ("efg", str5),
    ("efg", str22),
    ([],                                    tmpr),
    ([_SE(1,2,3,4)],                        tmpr),
    ([_SE(1,2,3,4), _SE(2,3,4,5)],          tmpr),
    ([_SE(1,2,3,4), _SE(1,0,3,0), _SE(2,3,4,5)], tmpr),
    (None,  int8_nullable),
])
def test_encode_decode_roundtrip(value, bsb_type):
    cmd = _cmd()
    for packettype in ("ret", "set"):
        enc = encode(value, bsb_type, cmd, validate=False, packettype=packettype)
        # Verify flag byte for types that carry one
        if packettype == "ret" and bsb_type.datatype not in (
            BsbDatatype.TimeProgram, BsbDatatype.String, BsbDatatype.Raw
        ):
            # nullable null in ret → flag=0x01; nullable non-null → enable_byte (0x06)
            # non-nullable non-null → 0x00
            if value is None:
                expected_flag = 0x01  # null: what a real controller sends
            elif bsb_type.nullable:
                expected_flag = bsb_type.enable_byte  # 0x06: value present for nullable
            else:
                expected_flag = 0x00  # value present for non-nullable
            assert enc[0] == expected_flag, \
                "packettype=ret: wrong flag for %r: got 0x%02x expected 0x%02x" % (
                    value, enc[0], expected_flag)
        got = decode(enc, bsb_type, packettype=packettype)
        assert got == value
        assert type(got) is type(value)


# ---------------------------------------------------------------------------
# encode() validation
# ---------------------------------------------------------------------------

def test_encode_readonly_command_raises():
    cmd = _cmd(flags=BsbCommandFlags.Readonly)
    with pytest.raises(ValidateError):
        encode(10, int8, cmd, validate=True)


def test_encode_non_nullable_none_raises():
    with pytest.raises(EncodeError):
        encode(None, int8, _cmd(), validate=False)


def test_encode_enum_invalid_value_raises():
    cmd = _cmd(enum={0: "off", 1: "on"})
    with pytest.raises(ValidateError):
        encode(99, enum, cmd, validate=True)


def test_encode_enum_string_label_resolved_to_int():
    """Passing a string label should be silently resolved to the integer index."""
    cmd = _cmd(enum={0: "Schutz", 1: "Automatik", 3: "Komfort"})
    result = encode("Automatik", enum, cmd, validate=True)
    # flag byte (0x01) + payload byte (0x01)
    assert result == bytes([0x01, 0x01])


def test_encode_enum_string_label_zero_resolved():
    """Label for index 0 (falsy) must resolve correctly."""
    cmd = _cmd(enum={0: "Schutz", 1: "Automatik"})
    result = encode("Schutz", enum, cmd, validate=True)
    assert result == bytes([0x01, 0x00])


def test_encode_enum_unknown_string_label_raises():
    """An unrecognised string label must raise ValidateError."""
    cmd = _cmd(enum={0: "off", 1: "on"})
    with pytest.raises(ValidateError):
        encode("maybe", enum, cmd, validate=True)


def test_encode_below_min_raises():
    cmd = _cmd(min_value=0.0, max_value=100.0)
    with pytest.raises(ValidateError):
        encode(-1.0, int16_10, cmd, validate=True)


def test_encode_above_max_raises():
    cmd = _cmd(min_value=0.0, max_value=100.0)
    with pytest.raises(ValidateError):
        encode(101.0, int16_10, cmd, validate=True)


def test_encode_flag_bytes_set_packet():
    cmd = _cmd()
    # Non-nullable, set → flag 0x01
    assert encode(10, int8, cmd, validate=False, packettype="set")[0] == 0x01
    # Nullable with value, set → flag 0x06
    assert encode(10, int8_nullable, cmd, validate=False, packettype="set")[0] == 0x06
    # Nullable with None, set → flag 0x05
    assert encode(None, int8_nullable, cmd, validate=False, packettype="set")[0] == 0x05


def test_encode_no_flag_byte_for_string_and_timeprogram():
    cmd = _cmd()
    # String: encoded bytes start directly with payload, no flag prefix
    enc_str = encode("abc", str5, cmd, validate=False, packettype="set")
    assert enc_str[0] == ord("a")
    # TimeProgram: starts with first slot byte directly
    enc_tmpr = encode([_SE(1, 2, 3, 4)], tmpr, cmd, validate=False, packettype="set")
    assert enc_tmpr[0] == 0x01  # h1=1 of the first entry


# ---------------------------------------------------------------------------
# BsbTelegram — serialize / deserialize
# ---------------------------------------------------------------------------

def test_telegram_get_serialize_structure():
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = t.serialize()
    assert raw[0] == 0xDC             # start marker
    assert raw[1] == 0x42 ^ 0x80     # src XOR 0x80
    assert raw[2] == 0x00             # dst
    assert raw[3] == len(raw)         # length field matches byte count
    assert raw[4] == 0x06             # packettype "get" = 6
    assert crc16xmodem(raw) == 0      # full frame including appended CRC = 0


def test_telegram_get_roundtrip():
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    device = {0x2D3D0490: cmd}
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = t.serialize()
    results = BsbTelegram.deserialize(raw, device)
    assert len(results) == 1
    t2 = results[0]
    assert isinstance(t2, BsbTelegram)
    assert t2.packettype == "get"
    assert t2.src == 0x42
    assert t2.dst == 0x00
    assert t2.command.telegram_id == 0x2D3D0490


def test_telegram_ret_roundtrip():
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    device = {0x2D3D0490: cmd}
    t = BsbTelegram(command=cmd, src=0x00, dst=0x42, packettype="ret", data=258)
    raw = t.serialize()
    assert crc16xmodem(raw) == 0
    results = BsbTelegram.deserialize(raw, device)
    assert len(results) == 1
    t2 = results[0]
    assert isinstance(t2, BsbTelegram)
    assert t2.packettype == "ret"
    assert t2.data == 258


def test_telegram_bad_crc_produces_no_telegram():
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = bytearray(t.serialize())
    raw[-1] ^= 0xFF  # corrupt last CRC byte
    results = BsbTelegram.deserialize(bytes(raw), {0x2D3D0490: cmd})
    assert not any(isinstance(r, BsbTelegram) for r in results)


def test_telegram_unknown_field_id():
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = t.serialize()
    results = BsbTelegram.deserialize(raw, {})   # empty device — ID not found
    assert len(results) == 1
    t2 = results[0]
    assert isinstance(t2, BsbTelegram)
    assert t2.command.disp_name == "unknown command"


def test_telegram_deserialize_multiple():
    """Two back-to-back telegrams in one buffer are both parsed."""
    cmd = BsbCommand(parameter=700, telegram_id=0x2D3D0490, bsb_type=int16)
    device = {0x2D3D0490: cmd}
    t = BsbTelegram(command=cmd, src=0x42, dst=0x00, packettype="get")
    raw = t.serialize() + t.serialize()
    results = BsbTelegram.deserialize(raw, device)
    telegrams = [r for r in results if isinstance(r, BsbTelegram)]
    assert len(telegrams) == 2
