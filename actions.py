"""Python hooks for the pad, for anything the GUI's shortcuts can't do.

Called before shortcuts.toml. Return True to say "handled", so the shortcut
(if any) isn't run as well. Changes apply on the next key press.
Watch presses arrive with: make logs
"""

from macropad import Press, notify, run  # noqa: F401


def on_press(press: Press):
    # Example:
    # if (press.layer, press.key) == (1, "k1"):
    #     notify("Hello from layer 1")
    #     return True
    return False


def on_release(press: Press):
    return False
