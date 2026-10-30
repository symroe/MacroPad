"""Read the keymap from the pad, and write keymap.py's layers to it."""

import importlib.util

from . import keycodes
from .layout import CONTROLS, LAYER_COUNT, MATRIX, ROTATIONS, SCRIPT, layer


def load_file(path):
    """Load LAYERS from a keymap.py."""
    spec = importlib.util.spec_from_file_location("user_keymap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    layers = module.LAYERS
    if len(layers) != LAYER_COUNT:
        raise ValueError(f"keymap.py must define {LAYER_COUNT} layers, not {len(layers)}")
    return layers


def resolve(layers):
    """Turn keymap layers into {(layer, control): code}, assigning SCRIPT codes."""
    pool = iter(keycodes.SCRIPT_POOL)
    codes = {}
    for n, controls in enumerate(layers):
        for control in CONTROLS:
            value = controls[control]
            if value == SCRIPT:
                try:
                    codes[n, control] = next(pool)
                except StopIteration:
                    raise ValueError("too many SCRIPT controls") from None
                continue
            code = keycodes.parse(value)
            if keycodes.is_script_code(code):
                raise ValueError(f"layer {n} {control}: F13-F24 are reserved for SCRIPT")
            codes[n, control] = code
    return codes


def read_device(via):
    """{(layer, control): code} as currently stored on the pad."""
    codes = {}
    for n in range(LAYER_COUNT):
        for control in CONTROLS:
            if control in MATRIX:
                codes[n, control] = via.get_key(n, *MATRIX[control])
            else:
                codes[n, control] = via.get_encoder(n, *ROTATIONS[control])
    return codes


def write_device(via, codes, dry_run=False):
    """Write the codes that differ from what's on the pad. Returns the changes."""
    current = read_device(via)
    changes = [(key, current[key], code) for key, code in codes.items() if current[key] != code]
    if not dry_run:
        for (n, control), _, code in changes:
            if control in MATRIX:
                via.set_key(n, *MATRIX[control], code)
            else:
                via.set_encoder(n, *ROTATIONS[control], code)
    return changes


def script_table(codes):
    """{code: (layer, control)} for every control that goes to the script."""
    return {code: key for key, code in codes.items() if keycodes.is_script_code(code)}


def render(codes):
    """Python source for a keymap.py matching codes, e.g. from read_device()."""
    defaults = layer()
    lines = ["LAYERS = ["]
    for n in range(LAYER_COUNT):
        lines.append(f"    # Layer {n}")
        lines.append("    layer(")
        for control in CONTROLS:
            code = codes[n, control]
            value = SCRIPT if keycodes.is_script_code(code) else keycodes.name(code)
            default = defaults[control]
            if value == default or value == repr(default):
                continue
            lines.append(f"        {control}={value},")
        lines.append("    ),")
    lines.append("]")
    return "from macropad import SCRIPT, layer\n\n" + "\n".join(lines) + "\n"
