"""What each control on the pad sends. Apply changes with `make push`.

    k1   k2   k3   k4      knob1   knob2
    k5   k6   k7   k8
    k9   k10  k11  k12         knob3
    k13  k14  k15  k16

Each knob has: knobN (press), knobN_left, knobN_right (turns).

Values:
    SCRIPT        -> goes to on_press() in actions.py (the default for keys)
    "KC_VOLU" etc -> a normal QMK keycode, handled by the pad itself
                     (see src/macropad/keycodes.py; knobs default to "KC_TRNS",
                     meaning "same as layer 0")

`make pull` prints what's on the pad now in this format.
"""

from macropad import SCRIPT, layer

LAYERS = [
    # Layer 0. Pressing knob2 steps through the layers.
    layer(
        knob1="KC_MPLY",
        knob1_left="KC_MPRV",
        knob1_right="KC_MNXT",
        knob2="TO(1)",
        knob2_left="KC_PGDN",
        knob2_right="KC_PGUP",
        knob3="KC_MUTE",
        knob3_left="KC_VOLD",
        knob3_right="KC_VOLU",
    ),
    # Layer 1
    layer(knob2="TO(2)"),
    # Layer 2
    layer(knob2="TO(3)"),
    # Layer 3: lighting controls (from DOIO's default keymap).
    layer(
        knob2="TO(0)",
        k1="RGB_SPI",
        k2="RGB_SPD",
        k5="RGB_SAI",
        k6="RGB_SAD",
        k9="RGB_TOG",
        k10="RGB_MOD",
        k11="RGB_HUI",
        k14="RGB_VAI",
        k15="RGB_HUD",
        k16="RGB_VAD",
    ),
]
