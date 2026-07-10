import os
import re
import tempfile
from pycparser.c_ast import Constant, Decl, FileAST, ID, InitList, BinaryOp
import json
import pycparser

g_AST: FileAST

c_src = """
#include <inttypes.h>
#define MAX_HEATINGTBL 500
#define DEFAULT_FLAG FL_SW_CTL_RONLY
#include "BSB_LAN_defs.h"
"""

def get_c_variable(var_name: str):
    for ext in g_AST.ext:
        if ext.name == var_name:
            return ext
    return None

def get_string(c_var: Decl) -> str:
  val = c_var.value
  if val.startswith('\"') and val.endswith('\"'):
    return val[1:-1]  # Remove surrounding quotes

def convert_flags(flags: int) -> list[str]:
  if (isinstance(flags, Constant)):
    int_flag = int(flags.value)
    match int_flag:
      case 1:    # FL_RONLY
        return ["READONLY"]
      case 2:    # FL_WONLY
        return ["WRITEONLY"]
      case 8:    # FL_OEM
        return ["OEM"]
      case 16:   # FL_SPECIAL_INF
        return ["SPECIAL_INF"]
      case 128:  # DEFAULT flag, aka FL_SW_CTL_RONLY
        return ["SW_CTL_RONLY"]
      case _:
        print("Unsupported flag format")
        return []
  elif (isinstance(flags, BinaryOp)) and flags.op == '+':
    return convert_flags(flags.left) + convert_flags(flags.right)
  else:
    print("Unsupported flag format")
    return []

def eval_flags(flags) -> int:
    """Recursively evaluate a pycparser flags expression to a plain integer."""
    if isinstance(flags, Constant):
        return int(flags.value, 0)
    elif isinstance(flags, BinaryOp):
        if flags.op == '+':
            return eval_flags(flags.left) + eval_flags(flags.right)
        elif flags.op == '<<':
            return eval_flags(flags.left) << eval_flags(flags.right)
    return 0


def get_enum(enumstr):
    enum_to_decode = enumstr.init.exprs[0].value
    enum_to_decode = get_string(enumstr.init.exprs[0])
    enum_values = enum_to_decode.split('\\0')
    enum_dict = {}
    for enum_value in enum_values:
      key_str, value = enum_value.split(' ', 1)
      if key_str.startswith('\\x'):
          key = int("0x" + key_str.replace('\\x', ''), 16)
      else:
          key = int(key_str)
      enum_dict[str(key)] = value
    return enum_dict

def get_categories(enum_cat_nr_var, enum_cat_var):
    """Returns list of (min, max, name) tuples for each category index."""
    nr_exprs = enum_cat_nr_var.init.exprs
    ranges = [(float(nr_exprs[i].value), float(nr_exprs[i+1].value))
              for i in range(0, len(nr_exprs) - 1, 2)]
    cat_str = get_string(enum_cat_var.init.exprs[0])
    cat_names = {}
    for entry in cat_str.split('\\0'):
        if not entry:
            continue
        key_part, _, name = entry.partition(' ')
        m = re.match(r'\\x([0-9A-Fa-f]{2})', key_part)
        if m:
            cat_names[int(m.group(1), 16)] = name
    return [(lo, hi, cat_names.get(i, '')) for i, (lo, hi) in enumerate(ranges)]


def category_for_param(param_nr, categories):
    for lo, hi, name in categories:
        if lo <= param_nr <= hi:
            return name
    return ''


def create_command(line, cmd, desc, flags) -> dict:
    flags_list = convert_flags(flags)
    return {
        "parameter": int(float(line.value)),
        "cmd":       cmd.value,
        "name":      get_string(get_c_variable(desc.name).init),
        "type":      "ENUM",  # default, overridden in main loop
        "readonly":  "READONLY" in flags_list or "SW_CTL_RONLY" in flags_list,
    }

def main():
    with tempfile.NamedTemporaryFile() as fp:
        fp.write(c_src.encode('utf-8'))
        fp.seek(0)
        global g_AST
        home_dir = os.environ.get('HOME')
        g_AST = pycparser.parse_file(fp.name, use_cpp=True, cpp_args= [r'-Itools/conf_lan2control', r'-I' + home_dir + '/BSB-LAN/BSB_LAN',r'-I/usr/share/python3-pycparser/fake_libc_include'])
        supported_cmd_types = json.loads(open('config/bsb-types.json').read())
        categories = get_categories(get_c_variable("ENUM_CAT_NR"), get_c_variable("ENUM_CAT"))
        cmdtbl = get_c_variable("cmdtbl")

        if not isinstance(cmdtbl, Decl) or cmdtbl.name != "cmdtbl":
            print("cmdtbl not found or not a Decl")
            return

        c_command: InitList # cmd_t
        bsb_commands = []
        enums = {}
        for c_command in cmdtbl.init.exprs:
            cmd: Constant = c_command.exprs[0]         # uint32_t cmd;         // the command or fieldID
            type: ID = c_command.exprs[1]              # uint8_t type;         // the message type
            line: Constant = c_command.exprs[2]        # float line;           // parameter number
            desc: ID = c_command.exprs[3]              # const char *desc;     // description test
            # enumstr_len: Constant = c_command.exprs[4] # uint16_t enumstr_len; // sizeof enum
            enumstr: Constant = c_command.exprs[5]     # const char *enumstr;  // enum string
            flags: Constant = c_command.exprs[6]       # uint32_t flags;       // e.g. FL_RONLY
            # dev_fam: Constant = c_command.exprs[7]     # uint8_t dev_fam;      // device family
            # dev_var: Constant = c_command.exprs[8]     # uint8_t dev_var;      // device variant
            if type.name[3:] not in supported_cmd_types:
                print(f"Unsupported command type: {type.name[3:]}")
                continue
            try:
                if int(cmd.value, 0) == 0:
                    print("Skipping CMD_UNKNOWN")
                    continue
            except ValueError:
                print("Invalid command value")
                continue

            command = create_command(line, cmd, desc, flags)
            command["type"] = type.name[3:]
            # FL_ENUM_X_2: bits 20-23 of flags encode the enum key width in bytes.
            # Y == 2 means the enum key is 2 bytes wide -> use ENUM_WORD.
            if command["type"] == "ENUM" and (eval_flags(flags) >> 20) & 0xF == 2:
                command["type"] = "ENUM_WORD"
            cat_name = category_for_param(command["parameter"], categories)
            if cat_name:
                command["name"] = command["name"] + " " + cat_name

            if command["type"] in ("ENUM", "ENUM_WORD"):
                enum_name = enumstr.name
                if enum_name not in enums:
                    enums[enum_name] = get_enum(get_c_variable(enumstr.name))
                command["enum"] = enum_name

            bsb_commands.append(command)

        with open("config/bsb_enums.cfg", "w") as f:
            for name, values in enums.items():
                f.write(name + "\t" + json.dumps(values, indent=2, ensure_ascii=False) + "\n")

        with open("config/bsb_fields.cfg", "w") as f:
            for command in bsb_commands:
                record = {"cmd": command["cmd"], "name": command["name"], "type": command["type"]}
                if command["type"] in ("ENUM", "ENUM_WORD"):
                    record["enum"] = command["enum"]
                if command["readonly"]:
                    record["readonly"] = True
                f.write(str(command["parameter"]) + "\t" + json.dumps(record, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()