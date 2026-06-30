import json

FIELDS_FILE = "config/bsb_fields.cfg"
ENUMS_FILE = "config/bsb_enums.cfg"

class BsBConfigReader:
    """Reads BSB field and enum definitions from the line-per-field config files."""

    def __init__(self):
        self._fields_path = FIELDS_FILE
        self._enums_path = ENUMS_FILE

    @staticmethod
    def _iter_records(f):
        """Yield (key, value_text) pairs from a multi-line key-value file.

        A new record begins at every line whose first character is NOT whitespace.
        Indented and empty continuation lines are accumulated into the value buffer
        and joined before JSON-parsing.

        Supports both compact and pretty-printed values:

            700 {"cmd":"2D3D0574",...}

            710     {
                      "cmd": "2D92058E",
                      ...
                    }
        """
        key = None
        buf = []
        for raw in f:
            c = raw[0] if raw else ''
            if c and (c == '_' or 'a' <= c <= 'z' or 'A' <= c <= 'Z' or '0' <= c <= '9'):
                if key is not None:
                    yield key, ''.join(buf)
                sep = raw.find(' ')
                if sep < 0:
                    sep = raw.find('\t')
                key = raw[:sep] if sep >= 0 else raw.rstrip()
                buf = [raw[sep + 1:] if sep >= 0 else '']
            elif key is not None:
                buf.append(raw)
        if key is not None:
            yield key, ''.join(buf)

    def load_fields(self, field_ids):
        """Load field definitions from the line-per-field text format.

        Scans the fields file line by line, parsing only the records whose
        parameter ID is in *field_ids*.  Stops as soon as all requested fields
        are found.  Enum string references are resolved from the enums file in
        a second pass.
        """
        wanted = {str(p): p for p in field_ids}
        result = {}

        with open(self._fields_path) as f:
            for key, value_text in self._iter_records(f):
                if key not in wanted:
                    continue
                param = wanted.pop(key)
                d = json.loads(value_text)
                result[param] = {
                    "id":             param,
                    "telegram_id":    bytes.fromhex(d["cmd"]),
                    "name":           d.get("name", str(param)),
                    "type_name":      d.get("type_name", ""),
                    "datatype":       d.get("datatype", ""),
                    "factor":         d.get("factor", 1),
                    "payload_length": d.get("payload_length", 0),
                    "unsigned":       d.get("unsigned", False),
                    "nullable":       d.get("nullable", False),
                    "unit":           d.get("unit", ""),
                    "enum":           d.get("enum"),   # string name until resolved
                    "min_value":      d.get("min_value"),
                    "max_value":      d.get("max_value"),
                    "readonly":       d.get("readonly", False),
                }
                if not wanted:
                    break

        needed_enums = {r["enum"] for r in result.values() if isinstance(r.get("enum"), str)}
        if needed_enums:
            with open(self._enums_path) as f:
                for key, value_text in self._iter_records(f):
                    if key not in needed_enums:
                        continue
                    vals = json.loads(value_text)
                    needed_enums.discard(key)
                    for r in result.values():
                        if r.get("enum") == key:
                            r["enum"] = {int(k): v for k, v in vals.items()}
                    if not needed_enums:
                        break

        for r in result.values():
            if isinstance(r.get("enum"), str):
                r["enum"] = None   # referenced enum name not found in enums file

        for fid in field_ids:
            if fid not in result:
                print("bsb_fields: field_id %d not found in fields file" % fid)

        return result
