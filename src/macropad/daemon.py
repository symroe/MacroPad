"""Grab the pad's keyboard interfaces and hand script presses to actions.py.

The pad shows up as several input devices. Only the keyboard ones are
grabbed; media and system keys come from separate devices, so they keep
working normally. Grabbed keys that aren't for the script (e.g. a knob set
to KC_PGUP) are passed back to the desktop through a virtual keyboard.

Each script press goes to actions.py first, then shortcuts.toml (the GUI's).
"""

import importlib.util
import logging
import queue
import select
import sys
import threading
import time
from pathlib import Path

import evdev
from evdev import ecodes

from . import keymap, shortcuts
from .helpers import Press, notify
from .via import PRODUCT_ID, VENDOR_ID, Via, ViaError

log = logging.getLogger("macropad")

FKEYS = {ecodes.KEY_F13 + i: 0x68 + i for i in range(12)}  # evdev -> QMK
MOD_BITS = {
    ecodes.KEY_LEFTCTRL: 0x01, ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT: 0x04, ecodes.KEY_LEFTMETA: 0x08,
    ecodes.KEY_RIGHTCTRL: 0x11, ecodes.KEY_RIGHTSHIFT: 0x12,
    ecodes.KEY_RIGHTALT: 0x14, ecodes.KEY_RIGHTMETA: 0x18,
}
# QMK sends a chord's modifiers in a report of their own just before the
# key, so modifier presses are held back this long in case F13-F24 follows.
MOD_HOLD_SECONDS = 0.05


class PadError(Exception):
    pass


def open_pad_devices():
    """Open the pad's keyboard interfaces."""
    devices = []
    for sys_dev in sorted(Path("/sys/class/input").glob("event*")):
        ids = sys_dev / "device/id"
        vendor, product = (int((ids / f).read_text(), 16) for f in ("vendor", "product"))
        if (vendor, product) != (VENDOR_ID, PRODUCT_ID):
            continue
        path = f"/dev/input/{sys_dev.name}"
        try:
            dev = evdev.InputDevice(path)
        except PermissionError:
            for d in devices:
                d.close()
            raise PadError(f"no permission to read {path}; run `sudo make install`") from None
        if ecodes.KEY_F13 in dev.capabilities().get(ecodes.EV_KEY, []):
            devices.append(dev)
        else:
            dev.close()
    if not devices:
        raise PadError("macropad not found (is it plugged in?)")
    return devices


class Pad:
    """One grabbed interface: which modifiers are down, and which belong to script chords."""

    def __init__(self, dev):
        self.dev = dev
        self.held = set()
        self.pending = []  # modifier presses held back
        self.pending_since = 0.0
        self.owned = set()  # modifiers swallowed as part of a chord
        self.down = {}  # F-key -> code it was pressed as, so releases match

    def handle(self, ev, out, codes):
        """Sort one key event into out (pass through) or codes: (code, is_press) for the script."""
        if ev.code in MOD_BITS:
            if ev.value == 1:
                self.held.add(ev.code)
                if not self.pending:
                    self.pending_since = time.monotonic()
                self.pending.append(ev)
            elif ev.value == 0:
                self.held.discard(ev.code)
                if ev.code in self.owned:
                    self.owned.discard(ev.code)
                elif any(p.code == ev.code for p in self.pending):
                    self.flush(out)
                    out.append(ev)
                else:
                    out.append(ev)
            elif ev.code not in self.owned and not self.pending:
                out.append(ev)
        elif ev.code in FKEYS:
            if ev.value == 1:
                mods = 0
                for code in self.held:
                    mods |= MOD_BITS[code]
                self.down[ev.code] = mods << 8 | FKEYS[ev.code]
                codes.append((self.down[ev.code], True))
                self.owned |= {p.code for p in self.pending}
                self.pending.clear()
            elif ev.value == 0 and ev.code in self.down:
                codes.append((self.down.pop(ev.code), False))
        else:
            self.flush(out)
            out.append(ev)

    def flush(self, out):
        out.extend(self.pending)
        self.pending.clear()


class Reloading:
    """A file that's loaded again whenever it changes. None if it doesn't exist."""

    def __init__(self, path, load):
        self.path = path
        self.load = load
        self.mtime = None
        self.value = None

    def get(self):
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            self.mtime = self.value = None
            return None
        if mtime != self.mtime:
            self.mtime = mtime
            try:
                self.value = self.load(self.path)
                log.info("loaded %s", self.path)
            except Exception:
                log.exception("couldn't load %s; keeping the previous version", self.path)
        return self.value


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dispatch(press, actions, store):
    module = actions.get()
    hook = getattr(module, "on_press" if press.down else "on_release", None)
    if hook and hook(press):
        return
    shortcut = store.get() and store.get().get(press.layer, press.key)
    if shortcut and shortcuts.is_complete(shortcut):
        (shortcuts.press if press.down else shortcuts.release)(shortcut, store.get().settings)
    elif press.down:
        notify("macropad", f"Layer {press.layer} {press.key} isn't set up yet. Open Macropad to set it up.")


def worker(presses, actions, store):
    while True:
        press = presses.get()
        try:
            dispatch(press, actions, store)
        except Exception:
            log.exception("failed handling %s", press)


def serve(presses):
    """Run until the pad goes away."""
    devices = open_pad_devices()
    ui = None
    try:
        with Via() as via:
            table = keymap.script_table(keymap.read_device(via))

        passthrough = set()
        for dev in devices:
            passthrough |= set(dev.capabilities()[ecodes.EV_KEY]) - set(FKEYS)
        try:
            ui = evdev.UInput({ecodes.EV_KEY: sorted(passthrough)}, name="macropad passthrough")
        except (OSError, evdev.UInputError) as e:
            log.warning("can't create virtual keyboard (%s); non-script keys will be ignored", e)

        for dev in devices:
            dev.grab()
        log.info("connected: %s; %d script controls", ", ".join(d.path for d in devices), len(table))

        pads = {dev.fd: Pad(dev) for dev in devices}
        while True:
            waiting = any(p.pending for p in pads.values())
            ready, _, _ = select.select(list(pads), [], [], MOD_HOLD_SECONDS if waiting else None)
            out, codes = [], []
            for fd in ready:
                pad = pads[fd]
                for ev in pad.dev.read():
                    if ev.type == ecodes.EV_KEY:
                        pad.handle(ev, out, codes)
            now = time.monotonic()
            for pad in pads.values():
                if pad.pending and now - pad.pending_since >= MOD_HOLD_SECONDS:
                    pad.flush(out)
            if ui:
                for ev in out:
                    ui.write(ecodes.EV_KEY, ev.code, ev.value)
                    ui.syn()
            for code, down in codes:
                if code in table:
                    layer, key = table[code]
                    log.info("layer %d %s %s", layer, key, "down" if down else "up")
                    presses.put(Press(layer, key, down))
                elif down:
                    log.warning("unknown key code 0x%04X; restart after `macropad push`", code)
    finally:
        for dev in devices:
            dev.close()
        if ui:
            ui.close()


def run(project_dir):
    sys.path.insert(0, str(project_dir))
    actions = Reloading(project_dir / "actions.py", load_module)
    store = Reloading(project_dir / "shortcuts.toml", shortcuts.Store)
    actions.get()
    store.get()
    presses = queue.Queue()
    threading.Thread(target=worker, args=(presses, actions, store), daemon=True).start()

    last_error = None
    while True:
        try:
            serve(presses)
        except (OSError, ViaError, PadError) as e:
            if str(e) != last_error:
                log.warning("%s; waiting for the pad", e)
                last_error = str(e)
            time.sleep(2)
