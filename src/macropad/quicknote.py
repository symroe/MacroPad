"""A small window for jotting a note, then sending it somewhere.

The note goes to today's Obsidian daily note (with the Obsidian CLI's
daily:append), or with --ticket is printed straight away as a Ticketr TODO
ticket, the first line being the title.

Ctrl+Enter sends it, Ctrl+K turns the line into a task (or back), Enter
continues a list, and Esc closes. Unsent text is kept as a draft for next time.
Spelling is checked against Obsidian's dictionary (see spelling.py).
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .gtk import Adw, Gdk, Gio, GLib, Gtk
from .spelling import SpellCheck

APP_ID = "uk.co.symroe.Macropad.Note"
CACHE = Path(GLib.get_user_cache_dir()) / "macropad"
# Its own venv's script, as the daemon's PATH may not include uv.
TICKETR = Path.home() / "Projects" / "Ticketr" / ".venv" / "bin" / "ticketr"
# indent, bullet, optional checkbox
LIST_ITEM = re.compile(r"^(\s*)([-*+] )(\[[ xX]\] )?")


def run_sender(argv, input=None):
    """Run a command, returning what went wrong, or None if it worked."""
    try:
        result = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or output.startswith("Error"):
        return output.splitlines()[-1] if output else "unknown error"
    return None


def add_to_daily_note(text):
    # daily:append adds one newline; the extra one leaves a blank line before the note.
    return run_sender(["obsidian", "daily:append", f"content=\n{text}"])


def print_ticket(text):
    title, _, description = text.partition("\n")
    # --force: a key press always means "print this", even if the title was used recently.
    return run_sender([str(TICKETR), "print", "-t", "todo", "--force", f"--title={LIST_ITEM.sub('', title).strip()}"],
                      input=description.strip())


@dataclass(frozen=True)
class Target:
    title: str
    subtitle: str
    verb: str  # on the button and in the hints
    failure: str  # shown before the error
    send: callable  # text -> error message, or None if it worked
    draft: Path
    shows_daily_note: bool = False


DAILY_NOTE = Target("Quick note", "Daily note", "Add", "Couldn't add note", add_to_daily_note,
                    CACHE / "note-draft.md", shows_daily_note=True)
TICKET = Target("Quick ticket", "Prints straight away. First line is the title", "Print", "Couldn't print ticket",
                print_ticket, CACHE / "ticket-draft.md")


class NoteWindow(Adw.ApplicationWindow):
    def __init__(self, app, target):
        super().__init__(application=app, title=target.title, default_width=560, default_height=320)
        self.target = target
        self.sent = False

        self.title = Adw.WindowTitle(title=target.title, subtitle=target.subtitle)
        add = Gtk.Button(label=target.verb, css_classes=["suggested-action"], tooltip_text="Ctrl+Enter")
        add.connect("clicked", lambda *_: self.send())
        header = Adw.HeaderBar(title_widget=self.title)
        header.pack_end(add)

        self.view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=12, bottom_margin=12,
                                 left_margin=12, right_margin=12)
        self.buffer = self.view.get_buffer()
        self.spelling = SpellCheck(self.view, self.show_error)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.view.add_controller(keys)

        hints = Gtk.Label(label=f"Ctrl+Enter {target.verb.lower()}  ·  Ctrl+K task  ·  Esc close",
                          css_classes=["caption", "dim-label"], margin_top=6, margin_bottom=6)
        view = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=self.view, vexpand=True))
        view.add_top_bar(header)
        view.add_bottom_bar(hints)
        self.toasts = Adw.ToastOverlay(child=view)
        self.set_content(self.toasts)

        self.load_draft()
        self.connect("close-request", lambda *_: self.save_draft())
        if target.shows_daily_note:
            self.show_note_name()

    # Keys

    def on_key(self, controller, keyval, keycode, state):
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if ctrl:
                self.send()
                return True
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False
            return self.continue_list()
        if ctrl and keyval in (Gdk.KEY_k, Gdk.KEY_K):
            self.toggle_task()
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def current_line(self):
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = cursor.copy()
        start.set_line_offset(0)
        end = cursor.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return start, cursor, end, self.buffer.get_text(start, end, False)

    def continue_list(self):
        """Enter on a list item starts another, or ends the list if the item is empty (like Obsidian)."""
        start, cursor, end, line = self.current_line()
        match = LIST_ITEM.match(line)
        if not match or cursor.get_line_offset() < match.end():
            return False
        if not line[match.end():].strip():
            self.buffer.delete(start, end)
            return True
        indent, bullet, checkbox = match.groups()
        self.buffer.insert_at_cursor("\n" + indent + bullet + ("[ ] " if checkbox else ""))
        self.view.scroll_mark_onscreen(self.buffer.get_insert())
        return True

    def toggle_task(self):
        """Make the current line a task, or a task back into plain text."""
        start, _, _, line = self.current_line()
        match = LIST_ITEM.match(line)
        indent = re.match(r"\s*", line).group()
        if match and match.group(3):
            old, new = match.group(0), indent
        elif match:
            old, new = match.group(0), indent + match.group(2) + "[ ] "
        else:
            old, new = indent, indent + "- [ ] "
        end = start.copy()
        end.forward_chars(len(old))
        self.buffer.delete(start, end)
        self.buffer.insert(start, new)

    # Sending and drafts

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False).strip()

    def send(self):
        text = self.text()
        if not text:
            self.close()
            return
        error = self.target.send(text)
        if error:
            self.show_error(f"{self.target.failure}: {error}")
            return
        self.sent = True
        self.close()

    def show_error(self, message):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(message), timeout=0))

    def load_draft(self):
        try:
            self.buffer.set_text(self.target.draft.read_text())
        except FileNotFoundError:
            return
        self.buffer.place_cursor(self.buffer.get_end_iter())

    def save_draft(self):
        if self.sent or not self.text():
            self.target.draft.unlink(missing_ok=True)
        else:
            self.target.draft.parent.mkdir(parents=True, exist_ok=True)
            self.target.draft.write_text(self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False))
        return False

    def show_note_name(self):
        """Show which note this goes to (e.g. "W44") without holding up the window."""
        proc = Gio.Subprocess.new(["obsidian", "daily:path"],
                                  Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)

        def done(proc, result):
            try:
                _, out, _ = proc.communicate_utf8_finish(result)
            except GLib.Error:
                return
            if out and out.strip().endswith(".md"):
                self.title.set_subtitle(out.strip().rsplit("/", 1)[-1].removesuffix(".md"))

        proc.communicate_utf8_async(None, None, done)


class NoteApp(Adw.Application):
    def __init__(self, target):
        self.target = target
        # Not single-instance: GNOME only gives focus to a new process's window,
        # not to an existing one raised from the background.
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        window = NoteWindow(self, self.target)
        window.present()
        window.view.grab_focus()


def run(ticket=False):
    NoteApp(TICKET if ticket else DAILY_NOTE).run([])
