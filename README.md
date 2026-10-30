# macropad

Shortcuts for a DOIO KB16 ("Megalodon") macro pad, set up in a small GNOME app
or in Python. The pad's keys never reach the desktop, so they can't clash with
other keyboards. Media keys and knobs (play/pause, volume…) work as normal.

```
k1   k2   k3   k4      knob1   knob2
k5   k6   k7   k8
k9   k10  k11  k12         knob3
k13  k14  k15  k16
```

## Getting started

Needs Ubuntu 24.04+ and [uv](https://docs.astral.sh/uv/):
`curl -LsSf https://astral.sh/uv/install.sh | sh`

```sh
sudo make install    # once per machine
make push            # write keymap.py to the pad
```

Then open **Macropad** from the app menu (or `make gui`), click a key, and pick
what it does. Changes save as you type and work on the next press.

## Day to day

| To…                             | Do this                                       |
|---------------------------------|-----------------------------------------------|
| Set up a key                    | Macropad app (`make gui`)                     |
| Do something the app can't      | Edit `actions.py` (Python, applies on save)   |
| Change what a key/knob sends    | Edit `keymap.py`, then `make push`            |
| See presses / errors            | `make logs`                                   |
| See what's on the pad now       | `make pull`                                   |
| Remove it all                   | `sudo make uninstall`                         |

Pressing knob2 steps through layers 0–3 (shown on the pad's screen).

## Actions

- **Open URL**: optionally in a Firefox container. The browser is set in Preferences.
- **Run command**: any shell command.
- **Run while held**: starts on press, stopped with Ctrl+C on release. For a
  voice memo: `pw-record ~/Memos/$(date +%F_%H-%M-%S).wav`
- **Quick note to Obsidian**: a small window (also `make note`). Ctrl+Enter
  adds the text to today's daily note via the `obsidian` CLI, Ctrl+K toggles a
  task, Enter continues a list, Esc closes and keeps a draft.

## Files

- `shortcuts.toml`: what the app edits. Fine to edit by hand. It's personal, so
  it isn't committed; `shortcuts.example.toml` shows the format.
- `actions.py`: Python hooks, run before `shortcuts.toml`; return `True` to say "handled".
- `keymap.py`: what the pad itself sends. Keys marked `SCRIPT` (the default)
  come to this program; anything else is handled by the pad.

New action types go in `ACTION_TYPES` in `src/macropad/shortcuts.py`; the app
builds its form from them.

## How it works

`make push` writes keycodes to the pad over VIA, giving each `SCRIPT` key its own
unused code (F13–F24 plus modifiers). A systemd user service grabs the pad's
keyboard devices, turns those codes back into `(layer, key)` presses and
releases, and passes other keys through. A udev rule lets your user (not root)
read the pad. The venv uses the system Python so the app can use Ubuntu's GTK
packages. Moved the folder or changed machine? Re-run `sudo make install`.
