"""QMK keycodes (the 16-bit values VIA reads and writes), by name.

Only the common ones are named; anything else can be written as an int.
Values follow QMK 0.19+ (VIA protocol 11+).
"""

import re

NAMES = {"KC_NO": 0x00, "KC_TRNS": 0x01}
NAMES |= {f"KC_{chr(c)}": 0x04 + i for i, c in enumerate(range(ord("A"), ord("Z") + 1))}
NAMES |= {f"KC_{n}": 0x1E + i for i, n in enumerate("1234567890")}
NAMES |= {f"KC_F{n}": 0x3A + n - 1 for n in range(1, 13)}
NAMES |= {f"KC_F{n}": 0x68 + n - 13 for n in range(13, 25)}
NAMES |= dict(
    KC_ENT=0x28, KC_ESC=0x29, KC_BSPC=0x2A, KC_TAB=0x2B, KC_SPC=0x2C,
    KC_MINS=0x2D, KC_EQL=0x2E, KC_LBRC=0x2F, KC_RBRC=0x30, KC_BSLS=0x31,
    KC_SCLN=0x33, KC_QUOT=0x34, KC_GRV=0x35, KC_COMM=0x36, KC_DOT=0x37,
    KC_SLSH=0x38, KC_CAPS=0x39, KC_PSCR=0x46, KC_SCRL=0x47, KC_PAUS=0x48,
    KC_INS=0x49, KC_HOME=0x4A, KC_PGUP=0x4B, KC_DEL=0x4C, KC_END=0x4D,
    KC_PGDN=0x4E, KC_RGHT=0x4F, KC_LEFT=0x50, KC_DOWN=0x51, KC_UP=0x52,
    KC_APP=0x65,
    # System and media keys arrive on separate USB interfaces that the
    # daemon leaves alone, so they always work, daemon or not.
    KC_PWR=0xA5, KC_SLEP=0xA6, KC_WAKE=0xA7, KC_MUTE=0xA8, KC_VOLU=0xA9,
    KC_VOLD=0xAA, KC_MNXT=0xAB, KC_MPRV=0xAC, KC_MSTP=0xAD, KC_MPLY=0xAE,
    KC_CALC=0xB2, KC_MFFD=0xBB, KC_MRWD=0xBC, KC_BRIU=0xBD, KC_BRID=0xBE,
    KC_LCTL=0xE0, KC_LSFT=0xE1, KC_LALT=0xE2, KC_LGUI=0xE3,
    KC_RCTL=0xE4, KC_RSFT=0xE5, KC_RALT=0xE6, KC_RGUI=0xE7,
    RGB_TOG=0x7820, RGB_MOD=0x7821, RGB_RMOD=0x7822, RGB_HUI=0x7823,
    RGB_HUD=0x7824, RGB_SAI=0x7825, RGB_SAD=0x7826, RGB_VAI=0x7827,
    RGB_VAD=0x7828, RGB_SPI=0x7829, RGB_SPD=0x782A,
)
CODES = {code: name for name, code in NAMES.items()}

# Modifier wrappers, e.g. C(KC_C) is Ctrl+C. Bit 0x10 marks right-hand mods.
MOD_WRAPPERS = {"C": 0x01, "S": 0x02, "A": 0x04, "G": 0x08}
# Layer functions, e.g. TO(1). The low 5 bits are the layer.
LAYER_FUNCS = {"TO": 0x5200, "MO": 0x5220, "DF": 0x5240, "TG": 0x5260, "OSL": 0x5280, "TT": 0x52C0}

# Codes the daemon hands to actions.py: F13-F24, alone or with modifiers.
# Ctrl+Alt combos come last as they're the most likely to mean something to
# the desktop if the daemon isn't running.
_FKEYS = [NAMES[f"KC_F{n}"] for n in range(13, 25)]
_POOL_MODS = [0x00, 0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x07]
SCRIPT_POOL = [mods << 8 | key for mods in _POOL_MODS for key in _FKEYS]


def is_script_code(code):
    return (code & 0xFF) in _FKEYS and code >> 8 <= 0x1F


def parse(value):
    """Turn a keymap value ("KC_A", "C(KC_C)", "TO(1)", 0x1234) into a code."""
    if isinstance(value, int):
        return value
    if value in NAMES:
        return NAMES[value]
    m = re.fullmatch(r"(\w+)\((.+)\)", value)
    if m and m[1] in MOD_WRAPPERS:
        return MOD_WRAPPERS[m[1]] << 8 | parse(m[2])
    if m and m[1] in LAYER_FUNCS:
        return LAYER_FUNCS[m[1]] | int(m[2])
    raise ValueError(f"unknown keycode: {value!r}")


def name(code):
    """The inverse of parse(): a readable name, or a hex int if unknown."""
    if code in CODES:
        return repr(CODES[code])
    for func, base in LAYER_FUNCS.items():
        if base <= code < base + 0x20:
            return repr(f"{func}({code - base})")
    if 0x0100 <= code < 0x2000 and (code & 0xFF) in CODES:
        inner = CODES[code & 0xFF]
        for wrapper, bit in MOD_WRAPPERS.items():
            if code >> 8 & bit:
                inner = f"{wrapper}({inner})"
        if not code >> 8 & 0x10:
            return repr(inner)
    return f"0x{code:04X}"
