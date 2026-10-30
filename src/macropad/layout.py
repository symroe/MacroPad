"""The pad's physical controls and where they live in the firmware.

Physical layout (keys on the left, knobs on the right):

    k1   k2   k3   k4      knob1   knob2
    k5   k6   k7   k8
    k9   k10  k11  k12         knob3
    k13  k14  k15  k16

Each knob has three controls: press ("knob1"), turn anticlockwise
("knob1_left") and turn clockwise ("knob1_right").

Matrix positions come from QMK's keyboards/doio/kb16/info.json.
"""

SCRIPT = "SCRIPT"
"""Keymap value meaning "send this press to actions.py"."""

LAYER_COUNT = 4

MATRIX = {f"k{n}": divmod(n - 1, 4) for n in range(1, 17)} | {
    "knob1": (0, 4),
    "knob2": (1, 4),
    "knob3": (2, 4),
}

# name -> (encoder index, clockwise)
ROTATIONS = {}
for _i, _knob in enumerate(["knob1", "knob2", "knob3"]):
    ROTATIONS[f"{_knob}_left"] = (_i, False)
    ROTATIONS[f"{_knob}_right"] = (_i, True)

KEYS = [name for name in MATRIX if name.startswith("k") and not name.startswith("knob")]
KNOB_CONTROLS = [c for k in ["knob1", "knob2", "knob3"] for c in (k, f"{k}_left", f"{k}_right")]
CONTROLS = KEYS + KNOB_CONTROLS


def layer(**controls):
    """One layer of the keymap.

    Keys you don't mention go to the script; knob controls you don't mention
    are transparent (they do whatever layer 0 does).
    """
    unknown = set(controls) - set(CONTROLS)
    if unknown:
        raise ValueError(f"unknown control(s): {', '.join(sorted(unknown))}")
    defaults = {k: SCRIPT for k in KEYS} | {k: "KC_TRNS" for k in KNOB_CONTROLS}
    return defaults | controls
