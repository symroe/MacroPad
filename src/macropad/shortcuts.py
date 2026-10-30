"""Shortcuts set up in the GUI, stored in shortcuts.toml, and the action types they use.

To add an action type, add an ActionType to ACTION_TYPES: the GUI builds its
form from `fields`, and the daemon calls `press` and `release`.
"""

import logging
import os
import shlex
import signal
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field

import tomli_w

from . import firefox

log = logging.getLogger("macropad")

HEADER = "# Shortcuts for the macro pad. Edited by `make gui`; hand edits are fine too.\n\n"


@dataclass
class Field:
    id: str
    title: str
    hint: str = ""
    optional: bool = False
    choices: callable = None  # settings -> list of allowed values, shown as a dropdown


@dataclass
class ActionType:
    title: str
    fields: list[Field]
    press: callable
    release: callable = None  # for actions that do something when the key is let go
    hint: str = ""


def _shell(command):
    return _spawn(["sh", "-c", command])


def _spawn(argv):
    return subprocess.Popen(
        argv,
        cwd=os.path.expanduser("~"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _open_url(shortcut, settings):
    url = shortcut["url"]
    if shortcut.get("container"):
        url = f"ext+container:name={shortcut['container']}&url={url}"
    browser = settings.get("browser") or "xdg-open"
    _shell(f"{browser} {shlex.quote(url)}")


def _run_command(shortcut, settings):
    _shell(shortcut["command"])


_held = {}  # shortcut id -> process started on press


def _start_held(shortcut, settings):
    _stop_held(shortcut, settings)
    _held[shortcut["id"]] = _shell(shortcut["command"])


def _stop_held(shortcut, settings):
    proc = _held.pop(shortcut["id"], None)
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            pass


def _quick_note(shortcut, settings):
    # Our own `macropad` script, next to the Python that's running this.
    _spawn([os.path.join(os.path.dirname(sys.executable), "macropad"), "note"])


ACTION_TYPES = {
    "url": ActionType(
        "Open URL",
        [
            Field("url", "URL"),
            Field(
                "container",
                "Firefox container",
                "Needs the “Open external links in a container” add-on",
                optional=True,
                choices=lambda settings: firefox.containers(settings.get("firefox_profile")),
            ),
        ],
        _open_url,
    ),
    "command": ActionType(
        "Run command",
        [Field("command", "Command", "Run with sh, from your home folder")],
        _run_command,
    ),
    "hold": ActionType(
        "Run while held",
        [Field("command", "Command", "Started on press, stopped with Ctrl+C on release")],
        _start_held,
        _stop_held,
        hint="e.g. a voice memo: pw-record ~/Memos/$(date +%F_%H-%M-%S).wav",
    ),
    "quicknote": ActionType(
        "Quick note to Obsidian",
        [],
        _quick_note,
        hint="Opens a small window; Ctrl+Enter adds the text to today's daily note",
    ),
}


def is_complete(shortcut):
    kind = ACTION_TYPES.get(shortcut.get("type"))
    return kind is not None and all(shortcut.get(f.id) or f.optional for f in kind.fields)


class Store:
    """shortcuts.toml: global settings plus one shortcut per (layer, key)."""

    def __init__(self, path):
        self.path = path
        self.settings = {}
        self.shortcuts = {}
        if path.exists():
            data = tomllib.loads(path.read_text())
            self.settings = data.get("settings", {})
            for item in data.get("shortcut", []):
                item = dict(item)
                self.shortcuts[item.pop("layer"), item.pop("key")] = item

    def get(self, layer, key):
        shortcut = self.shortcuts.get((layer, key))
        if shortcut is None:
            return None
        return shortcut | {"id": f"{layer}.{key}"}

    def set(self, layer, key, shortcut):
        if shortcut:
            self.shortcuts[layer, key] = shortcut
        else:
            self.shortcuts.pop((layer, key), None)

    def save(self):
        items = [
            {"layer": layer, "key": key, **values}
            for (layer, key), values in sorted(self.shortcuts.items(), key=_sort_key)
        ]
        text = tomli_w.dumps({"settings": self.settings, "shortcut": items})
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(HEADER + text)
        tmp.replace(self.path)


def _sort_key(item):
    (layer, key), _ = item
    return layer, int(key[1:]) if key[1:].isdigit() else 100, key


def press(shortcut, settings):
    if shortcut and is_complete(shortcut):
        ACTION_TYPES[shortcut["type"]].press(shortcut, settings)


def release(shortcut, settings):
    if shortcut and is_complete(shortcut) and ACTION_TYPES[shortcut["type"]].release:
        ACTION_TYPES[shortcut["type"]].release(shortcut, settings)
