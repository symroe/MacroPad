"""Spell checking for a Gtk.TextView, using Obsidian's dictionary.

Obsidian (being Chromium) lists its languages in Preferences and its added words
in "Custom Dictionary.txt". Its language files (.bdic) are in a format only
Chromium reads, so the language itself comes from the matching system Hunspell
dictionary, through enchant. Added words are read when the window opens.

Words added here go straight into Obsidian's file. Obsidian only starts using
them after a restart.

Misspelled words get a red underline. Right-clicking one offers suggestions and
adding it to Obsidian's dictionary.
"""

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path

from .gtk import Gdk, Gio, GLib, Gtk, Pango

try:
    import enchant
except ImportError:  # the C library is missing; the window still works without checking
    enchant = None

log = logging.getLogger("macropad")

OBSIDIAN = Path(GLib.get_user_config_dir()) / "obsidian"
CUSTOM_WORDS = "Custom Dictionary.txt"
CHECKSUM_PREFIX = "checksum_v1 = "
DEFAULT_LANGUAGES = ["en-GB"]
CHECK_DELAY_MS = 250
MAX_SUGGESTIONS = 5

WORD = re.compile(r"(?<!\w)[^\W\d_]+(?:['’][^\W\d_]+)*(?!\w)")
# Markdown that isn't prose: URLs, email addresses, `code`, [[links]] and #tags.
NOT_PROSE = re.compile(r"https?://\S+|\S+@\S+|`[^`\n]*`|\[\[[^\]\n]*\]\]|(?<!\w)#\S+")


def obsidian_languages(config=OBSIDIAN):
    try:
        languages = json.loads((config / "Preferences").read_text())["spellcheck"]["dictionaries"]
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_LANGUAGES
    return languages or DEFAULT_LANGUAGES


def read_words(path):
    # The file ends with a line holding Chromium's checksum.
    lines = path.read_text(encoding="utf-8").split("\n")
    return [line for line in lines if line and not line.startswith(CHECKSUM_PREFIX)]


def obsidian_words(config=OBSIDIAN):
    try:
        return read_words(config / CUSTOM_WORDS)
    except (OSError, UnicodeError):
        return []


def write_word(word, config=OBSIDIAN):
    """Add a word to Obsidian's file, the way Chromium does: byte-sorted words, a
    checksum, and the previous version kept as .backup."""
    path = config / CUSTOM_WORDS
    try:
        words = set(read_words(path))
    except FileNotFoundError:
        words = set()  # anything else raises: rewriting would lose what's in there
    if word in words:
        return
    body = "".join(f"{each}\n" for each in sorted(words | {word}, key=str.encode))
    checksum = hashlib.md5(body.encode()).hexdigest()
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.backup"))
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.touch(mode=0o600)
    tmp.write_text(f"{body}{CHECKSUM_PREFIX}{checksum}", encoding="utf-8")
    tmp.replace(path)


def load_dictionaries(config=OBSIDIAN):
    """Enchant dictionaries for Obsidian's languages, including its added words."""
    if enchant is None:
        log.warning("spell checking is off: the enchant library is missing")
        return []
    tags = [language.replace("-", "_") for language in obsidian_languages(config)]
    dictionaries = [enchant.Dict(tag) for tag in tags if enchant.dict_exists(tag)]
    if not dictionaries:
        log.warning("spell checking is off: no system dictionary for %s", ", ".join(tags))
    for dictionary in dictionaries:
        for word in obsidian_words(config):
            dictionary.add_to_session(word)
    return dictionaries


def plain_apostrophes(word):
    return word.replace("’", "'")


class SpellCheck:
    def __init__(self, view, on_error, config=OBSIDIAN):
        self.view = view
        self.on_error = on_error
        self.config = config
        self.buffer = view.get_buffer()
        self.dictionaries = load_dictionaries(config)
        self.pending = None
        self.replacing = None  # (start, end) offsets of the word the menu is for
        if not self.dictionaries:
            return

        red = Gdk.RGBA()
        red.parse("#e01b24")
        self.tag = self.buffer.create_tag("misspelled", underline=Pango.Underline.ERROR, underline_rgba=red)
        self.buffer.connect("changed", self.schedule)
        self.buffer.connect("notify::cursor-position", self.schedule)

        replace = Gio.SimpleAction.new("replace", GLib.VariantType.new("s"))
        replace.connect("activate", self.on_replace)
        add = Gio.SimpleAction.new("add", GLib.VariantType.new("s"))
        add.connect("activate", self.on_add)
        actions = Gio.SimpleActionGroup()
        actions.add_action(replace)
        actions.add_action(add)
        view.insert_action_group("spell", actions)

        # In the capture phase, so the menu is ready before the view opens it.
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self.on_right_click)
        view.add_controller(click)

    def is_correct(self, word):
        word = plain_apostrophes(word)
        return any(dictionary.check(word) for dictionary in self.dictionaries)

    def misspellings(self):
        """(start, end) offsets of each misspelled word."""
        text = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)
        prose = NOT_PROSE.sub(lambda match: " " * len(match.group()), text)
        return [match.span() for match in WORD.finditer(prose) if not self.is_correct(match.group())]

    # Underlines

    def schedule(self, *_):
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(CHECK_DELAY_MS, self.check)

    def check(self):
        self.pending = None
        cursor = self.buffer.get_property("cursor-position")
        self.buffer.remove_tag(self.tag, self.buffer.get_start_iter(), self.buffer.get_end_iter())
        for start, end in self.misspellings():
            if end != cursor:  # still being typed
                self.buffer.apply_tag(self.tag, self.buffer.get_iter_at_offset(start),
                                      self.buffer.get_iter_at_offset(end))
        return GLib.SOURCE_REMOVE

    # Right-click menu

    def on_right_click(self, gesture, presses, x, y):
        self.replacing = None
        self.view.set_extra_menu(None)
        x, y = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, where = self.view.get_iter_at_location(x, y)
        if not found:
            return
        offset = where.get_offset()
        for start, end in self.misspellings():
            if start <= offset < end:
                self.replacing = start, end
                self.view.set_extra_menu(self.suggestions_menu(start, end))
                return

    def suggestions_menu(self, start, end):
        word = self.buffer.get_text(self.buffer.get_iter_at_offset(start), self.buffer.get_iter_at_offset(end), False)
        suggestions = Gio.Menu()
        for suggestion in self.dictionaries[0].suggest(word)[:MAX_SUGGESTIONS]:
            item = Gio.MenuItem.new(suggestion.replace("_", "__"), None)
            item.set_action_and_target_value("spell.replace", GLib.Variant.new_string(suggestion))
            suggestions.append_item(item)
        if not suggestions.get_n_items():
            suggestions.append("No suggestions", "spell.none")  # no such action, so it shows greyed out

        word = plain_apostrophes(word)
        add = Gio.MenuItem.new(f"Add “{word}” to Obsidian's dictionary", None)
        add.set_action_and_target_value("spell.add", GLib.Variant.new_string(word))
        menu = Gio.Menu()
        menu.append_section(None, suggestions)
        menu.append_item(add)
        return menu

    def on_replace(self, action, suggestion):
        start, end = self.replacing
        start, end = self.buffer.get_iter_at_offset(start), self.buffer.get_iter_at_offset(end)
        self.buffer.begin_user_action()
        self.buffer.delete(start, end)
        self.buffer.insert(start, suggestion.get_string())
        self.buffer.end_user_action()

    def on_add(self, action, word):
        word = word.get_string()
        try:
            write_word(word, self.config)
        except (OSError, UnicodeError) as e:
            self.on_error(f"Couldn't add “{word}” to the dictionary: {e}")
            return
        for dictionary in self.dictionaries:
            dictionary.add_to_session(word)
        self.check()
