"""Small helpers for actions.py."""

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Press:
    layer: int
    key: str  # "k1".."k16", "knob1", "knob1_left", "knob1_right", ...
    down: bool = True  # False when the key is released


def run(*cmd):
    """Start a program in the background, e.g. run("firefox", url)."""
    subprocess.Popen(
        [os.path.expanduser(str(cmd[0])), *map(str, cmd[1:])],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_url(url):
    """Open a URL in the default browser."""
    run("xdg-open", url)


def notify(title, body=""):
    """Show a desktop notification."""
    run("notify-send", "--app-name=macropad", title, body)
