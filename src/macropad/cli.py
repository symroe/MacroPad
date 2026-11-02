import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import keycodes, keymap
from .via import Via, ViaError


def project_dir():
    path = Path(os.environ.get("MACROPAD_DIR", Path.cwd()))
    if not (path / "keymap.py").exists():
        sys.exit(f"no keymap.py in {path}; run from the project folder or set MACROPAD_DIR")
    return path


def cmd_run(args):
    from . import daemon

    daemon.run(project_dir())


def cmd_gui(args):
    from . import gui

    gui.run(project_dir())


def cmd_note(args):
    from . import quicknote

    quicknote.run(ticket=args.ticket)


def cmd_push(args):
    codes = keymap.resolve(keymap.load_file(project_dir() / "keymap.py"))
    with Via() as via:
        changes = keymap.write_device(via, codes, dry_run=args.dry_run)
    for (layer, control), old, new in changes:
        print(f"layer {layer} {control}: {keycodes.name(old)} -> {keycodes.name(new)}")
    if not changes:
        print("pad already matches keymap.py")
    elif args.dry_run:
        print("(dry run, nothing written)")
    else:
        # The daemon reads the keymap from the pad when it connects.
        subprocess.run(["systemctl", "--user", "try-restart", "macropad.service"], check=False)
        print(f"wrote {len(changes)} change(s)")


def cmd_pull(args):
    with Via() as via:
        print(keymap.render(keymap.read_device(via)), end="")


def main():
    parser = argparse.ArgumentParser(prog="macropad")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("run", help="run the daemon (normally started by systemd)").set_defaults(func=cmd_run)
    push = sub.add_parser("push", help="write keymap.py to the pad")
    push.add_argument("--dry-run", action="store_true", help="show changes without writing them")
    push.set_defaults(func=cmd_push)
    sub.add_parser("pull", help="print the pad's current keymap as Python").set_defaults(func=cmd_pull)
    sub.add_parser("gui", help="set up shortcuts in a window").set_defaults(func=cmd_gui)
    note = sub.add_parser("note", help="jot a note into today's Obsidian daily note")
    note.add_argument("--ticket", action="store_true", help="print it as a Ticketr TODO ticket instead")
    note.set_defaults(func=cmd_note)
    args = parser.parse_args()

    # Under systemd the journal adds timestamps itself.
    fmt = "%(message)s" if "JOURNAL_STREAM" in os.environ else "%(asctime)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    try:
        args.func(args)
    except (ViaError, ValueError) as e:
        sys.exit(f"error: {e}")
    except KeyboardInterrupt:
        pass
