# Tests for bsb_fields.py
# These are integration-style tests: they load the real device model JSON files
# and verify that load_fields() returns correct, well-formed field dicts.

import pytest
import bsb.fields as bsb_fields

# Whitelisted IDs used on the actual device
_FIELD_IDS = [700, 710, 8700, 8743]

# Required keys every field dict must contain
_REQUIRED_KEYS = {
    "id", "telegram_id", "name", "type_name", "datatype",
    "factor", "payload_length", "unsigned", "nullable", "unit",
    "enum", "min_value", "max_value", "readonly",
}


@pytest.fixture(scope="module")
def fields():
    return bsb_fields.BsBConfigReader().load_fields(_FIELD_IDS)


# ---------------------------------------------------------------------------
# Basic shape
# ---------------------------------------------------------------------------

def test_all_whitelisted_ids_present(fields):
    assert set(fields.keys()) == set(_FIELD_IDS)


def test_each_field_has_required_keys(fields):
    for fid, f in fields.items():
        missing = _REQUIRED_KEYS - f.keys()
        assert not missing, "Field %d missing keys: %s" % (fid, missing)


def test_field_id_matches_dict_key(fields):
    for fid, f in fields.items():
        assert f["id"] == fid


def test_telegram_id_is_4_bytes(fields):
    for fid, f in fields.items():
        assert isinstance(f["telegram_id"], bytes), "Field %d: telegram_id not bytes" % fid
        assert len(f["telegram_id"]) == 4, "Field %d: telegram_id not 4 bytes" % fid


def test_field_name_is_nonempty_string(fields):
    for fid, f in fields.items():
        assert isinstance(f["name"], str) and f["name"], "Field %d: name empty or not str" % fid


# ---------------------------------------------------------------------------
# Field 700 — Operating mode (ENUM, writable, has inline enum dict)
# ---------------------------------------------------------------------------

def test_field_700_datatype_is_enum(fields):
    assert fields[700]["datatype"] == "ENUM"


def test_field_700_has_enum_dict_with_int_keys(fields):
    enum = fields[700]["enum"]
    assert enum is not None, "Field 700 enum should not be None"
    assert len(enum) > 0
    for k in enum:
        assert isinstance(k, int), "Enum key %r is not int" % k


def test_field_700_is_not_readonly(fields):
    assert fields[700]["readonly"] is False


def test_field_700_payload_length_1(fields):
    assert fields[700]["payload_length"] == 1


# ---------------------------------------------------------------------------
# Field 710 — Comfort setpoint (TEMP/VALS, factor=64, unit=°C)
# ---------------------------------------------------------------------------

def test_field_710_datatype_is_vals(fields):
    assert fields[710]["datatype"] == "VALS"


def test_field_710_factor_64(fields):
    assert fields[710]["factor"] == 64


def test_field_710_unit_celsius(fields):
    assert "°C" in fields[710]["unit"]


def test_field_710_payload_length_2(fields):
    assert fields[710]["payload_length"] == 2


def test_field_710_no_enum(fields):
    assert fields[710]["enum"] is None


# ---------------------------------------------------------------------------
# Field 8700 — Outside temperature (read-only sensor)
# ---------------------------------------------------------------------------

def test_field_8700_is_readonly(fields):
    assert fields[8700]["readonly"] is True


def test_field_8700_datatype_is_vals(fields):
    assert fields[8700]["datatype"] == "VALS"


def test_field_8700_unit_celsius(fields):
    assert "°C" in fields[8700]["unit"]


# ---------------------------------------------------------------------------
# Field 8743 — Flow temperature setpoint (read-only sensor)
# ---------------------------------------------------------------------------

def test_field_8743_is_readonly(fields):
    assert fields[8743]["readonly"] is True


def test_field_8743_factor_64(fields):
    assert fields[8743]["factor"] == 64


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_unknown_id_is_not_returned():
    result = bsb_fields.BsBConfigReader().load_fields([99999])
    assert 99999 not in result


def test_empty_whitelist_returns_empty_dict():
    result = bsb_fields.BsBConfigReader().load_fields([])
    assert result == {}


def test_subset_of_ids():
    result = bsb_fields.BsBConfigReader().load_fields([700])
    assert list(result.keys()) == [700]
    assert result[700]["datatype"] == "ENUM"
