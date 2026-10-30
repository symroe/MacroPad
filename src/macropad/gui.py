"""A GTK 4 / libadwaita app for setting up the shortcuts in shortcuts.toml.

Changes are saved as you type; the daemon picks them up on the next press.
"""

from . import firefox, keycodes, keymap, shortcuts
from .gtk import Adw, Gdk, Gio, GLib, Gtk, Pango
from .layout import KEYS, LAYER_COUNT, SCRIPT

APP_ID = "uk.co.symroe.Macropad"

CSS = """
.pad-key { min-width: 84px; min-height: 84px; padding: 6px; border-radius: 12px; }
.pad-knob { min-width: 76px; min-height: 76px; padding: 4px; border-radius: 9999px; }
.pad-knob.big { min-width: 108px; min-height: 108px; }
.pad-title { font-weight: bold; }
"""

KNOB_PARTS = [("", "Press"), ("_left", "Turn left"), ("_right", "Turn right")]


FRIENDLY = {
    "MPLY": "Play/Pause", "MNXT": "Next track", "MPRV": "Previous track", "MSTP": "Stop",
    "MUTE": "Mute", "VOLU": "Volume up", "VOLD": "Volume down", "PGUP": "Page up",
    "PGDN": "Page down", "NO": "Nothing", "TRNS": "Layer 0",
}


def pretty(value):
    name = keycodes.name(keycodes.parse(value)).strip("'").removeprefix("KC_")
    if name.startswith("TO("):
        return f"Layer {name[3:-1]}"
    return FRIENDLY.get(name, name)


class Window(Adw.ApplicationWindow):
    def __init__(self, app, project_dir):
        super().__init__(application=app, title="Macropad", default_width=1000, default_height=620)
        self.store = shortcuts.Store(project_dir / "shortcuts.toml")
        self.layers = keymap.load_file(project_dir / "keymap.py")
        self.project_dir = project_dir
        self.layer = 0
        self.selected = "k1"
        self.buttons = {}
        self.save_pending = None
        self.connect("close-request", lambda *_: self.save_now())

        header = Adw.HeaderBar()
        switcher = Gtk.Box(css_classes=["linked"])
        first = None
        for n in range(LAYER_COUNT):
            button = Gtk.ToggleButton(label=f"Layer {n}", active=n == 0, group=first)
            button.connect("toggled", self.on_layer_toggled, n)
            switcher.append(button)
            first = first or button
        header.set_title_widget(switcher)

        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu.append("Open Project Folder", "win.open-folder")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True))
        self.add_action_callback("preferences", self.show_preferences)
        self.add_action_callback("open-folder", self.open_folder)

        keys = Gtk.Grid(row_spacing=8, column_spacing=8)
        for name in KEYS:
            row, col = divmod(int(name[1:]) - 1, 4)
            keys.attach(self.pad_button(name, ["pad-key"]), col, row, 1, 1)
        knobs = Gtk.Grid(row_spacing=28, column_spacing=20, valign=Gtk.Align.START)
        knobs.attach(self.pad_button("knob1", ["pad-knob"]), 0, 0, 1, 1)
        knobs.attach(self.pad_button("knob2", ["pad-knob"]), 1, 0, 1, 1)
        knobs.attach(self.pad_button("knob3", ["pad-knob", "big"], halign=Gtk.Align.CENTER), 0, 1, 2, 1)
        pad = Gtk.Box(spacing=36, margin_start=36, margin_end=36, valign=Gtk.Align.CENTER)
        pad.append(keys)
        pad.append(knobs)

        self.editor = Adw.Bin(hexpand=True, width_request=380)
        body = Gtk.Box()
        body.append(pad)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self.editor)

        view = Adw.ToolbarView(content=body)
        view.add_top_bar(header)
        self.set_content(view)
        self.refresh()

    def add_action_callback(self, name, callback):
        action = Gio.SimpleAction(name=name)
        action.connect("activate", lambda *_: callback())
        self.add_action(action)

    # The pad

    def pad_button(self, control, classes, **kwargs):
        title = Gtk.Label(css_classes=["pad-title"], ellipsize=Pango.EllipsizeMode.END, max_width_chars=9, wrap=True, lines=2,
                          justify=Gtk.Justification.CENTER)
        subtitle = Gtk.Label(css_classes=["caption", "dim-label"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2)
        box.append(title)
        box.append(subtitle)
        button = Gtk.Button(child=box, css_classes=classes, **kwargs)
        button.connect("clicked", self.on_select, control)
        self.buttons[control] = (button, title, subtitle)
        return button

    def effective(self, control):
        """(layer, value) actually used for control on the current layer: KC_TRNS falls through to layer 0."""
        value = self.layers[self.layer][control]
        if self.layer and value != SCRIPT and keycodes.parse(value) == keycodes.NAMES["KC_TRNS"]:
            return 0, self.layers[0][control]
        return self.layer, value

    def describe(self, control):
        layer, value = self.effective(control)
        if value != SCRIPT:
            return pretty(value), "pad"
        shortcut = self.store.shortcuts.get((layer, control), {})
        if shortcut.get("label"):
            return shortcut["label"], control
        if shortcut.get("type"):
            return shortcuts.ACTION_TYPES[shortcut["type"]].title, control
        return "—", control

    def refresh(self):
        for control, (button, title, subtitle) in self.buttons.items():
            title.set_label(self.describe(control)[0])
            subtitle.set_label(control)
            if control == self.selected:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")

    def on_layer_toggled(self, button, n):
        if button.get_active():
            self.layer = n
            self.refresh()
            self.show_editor()

    def on_select(self, button, control):
        self.selected = control
        self.refresh()
        self.show_editor()

    # The editor

    def show_editor(self):
        page = Adw.PreferencesPage()
        if self.selected.startswith("knob"):
            for suffix, title in KNOB_PARTS:
                page.add(self.control_group(self.selected + suffix, f"{self.selected} · {title}"))
        else:
            page.add(self.control_group(self.selected, self.selected))
        self.editor.set_child(page)

    def control_group(self, control, title):
        layer, value = self.effective(control)
        group = Adw.PreferencesGroup(title=f"{title} · Layer {self.layer}")
        if layer != self.layer:
            group.set_description("Same as layer 0")
        if value != SCRIPT:
            group.add(Adw.ActionRow(
                title=f"Sends {pretty(value)}",
                subtitle="Handled by the pad itself. Change this in keymap.py, then run make push.",
            ))
            return group

        shortcut = self.store.shortcuts.get((layer, control), {})
        kind = shortcuts.ACTION_TYPES.get(shortcut.get("type"))

        name = Adw.EntryRow(title="Name", text=shortcut.get("label", ""))
        name.connect("changed", lambda row: self.update(layer, control, label=row.get_text()))
        group.add(name)

        type_ids = [None, *shortcuts.ACTION_TYPES]
        titles = ["Nothing"] + [t.title for t in shortcuts.ACTION_TYPES.values()]
        action = Adw.ComboRow(title="Action", model=Gtk.StringList.new(titles))
        action.set_selected(type_ids.index(shortcut.get("type")) if kind else 0)
        action.connect("notify::selected", lambda row, _: self.change_type(layer, control, type_ids[row.get_selected()]))
        group.add(action)

        if kind:
            if kind.hint:
                group.set_description(kind.hint)
            for field in kind.fields:
                group.add(self.field_row(layer, control, field, shortcut.get(field.id, "")))
            group.add(self.try_row(layer, control, kind.release is not None))
        return group

    def field_row(self, layer, control, field, value):
        title = field.title + (" (optional)" if field.optional else "")
        if field.choices:
            # Keep the current value even if it's no longer offered, so opening the app never loses it.
            choices = field.choices(self.store.settings)
            values = ([""] if field.optional else []) + choices + ([value] if value and value not in choices else [])
            labels = ["None" if v == "" else v for v in values]
            row = Adw.ComboRow(title=title, subtitle=field.hint, model=Gtk.StringList.new(labels))
            row.set_selected(values.index(value) if value in values else 0)
            if not field.optional and not value and values:
                self.update(layer, control, **{field.id: values[0]})
            row.connect("notify::selected", lambda r, _: self.update(layer, control, **{field.id: values[r.get_selected()]}))
            return row
        row = Adw.EntryRow(title=title, text=value)
        if field.hint:
            row.add_suffix(Gtk.Image(icon_name="dialog-information-symbolic", tooltip_text=field.hint))
        row.connect("changed", lambda r: self.update(layer, control, **{field.id: r.get_text()}))
        return row

    def try_row(self, layer, control, holdable):
        """A button that presses (and, when let go, releases) the shortcut."""
        button = Gtk.Button(label="Try", valign=Gtk.Align.CENTER)
        gesture = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)

        def pressed(gesture, *_):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            button.set_state_flags(Gtk.StateFlags.ACTIVE, False)
            shortcuts.press(self.store.get(layer, control), self.store.settings)

        def released(*_):
            button.unset_state_flags(Gtk.StateFlags.ACTIVE)
            shortcuts.release(self.store.get(layer, control), self.store.settings)

        gesture.connect("pressed", pressed)
        gesture.connect("released", released)
        button.add_controller(gesture)
        row = Adw.ActionRow(title="Try it now", subtitle="Hold the button to keep it running" if holdable else "")
        row.add_suffix(button)
        return row

    def update(self, layer, control, **changes):
        shortcut = self.store.shortcuts.get((layer, control), {})
        shortcut |= changes
        shortcut = {k: v for k, v in shortcut.items() if v}
        self.store.set(layer, control, shortcut)
        self.schedule_save()
        self.refresh()

    def change_type(self, layer, control, type_id):
        shortcut = self.store.shortcuts.get((layer, control), {})
        keep = {"label"} | {f.id for f in shortcuts.ACTION_TYPES[type_id].fields} if type_id else {"label"}
        shortcut = {k: v for k, v in shortcut.items() if k in keep}
        if type_id:
            shortcut["type"] = type_id
        self.store.set(layer, control, shortcut)
        self.schedule_save()
        self.refresh()
        GLib.idle_add(self.show_editor)

    # Saving and settings

    def schedule_save(self):
        if self.save_pending:
            GLib.source_remove(self.save_pending)
        self.save_pending = GLib.timeout_add(400, self.save_now)

    def save_now(self):
        if self.save_pending:
            GLib.source_remove(self.save_pending)
            self.save_pending = None
            self.store.save()
        return False

    def show_preferences(self):
        browser = Adw.EntryRow(title="Browser command", text=self.store.settings.get("browser", ""))
        browser.add_suffix(Gtk.Image(
            icon_name="dialog-information-symbolic",
            tooltip_text="Used by “Open URL”, with the URL added to the end. Leave empty for your default browser.",
        ))
        browser.connect("changed", self.on_browser_changed)
        names = list(firefox.profiles())
        values = [""] + names
        current = self.store.settings.get("firefox_profile", "")
        profile = Adw.ComboRow(title="Firefox profile", subtitle="Where the container list comes from",
                               model=Gtk.StringList.new(["All profiles"] + names))
        profile.set_selected(values.index(current) if current in values else 0)
        profile.connect("notify::selected", lambda r, _: self.set_setting("firefox_profile", values[r.get_selected()]))
        group = Adw.PreferencesGroup(title="Opening URLs")
        group.add(browser)
        group.add(profile)
        page = Adw.PreferencesPage()
        page.add(group)
        dialog = Adw.PreferencesDialog()
        dialog.add(page)
        dialog.present(self)

    def on_browser_changed(self, row):
        self.set_setting("browser", row.get_text())

    def set_setting(self, name, value):
        if value:
            self.store.settings[name] = value
        else:
            self.store.settings.pop(name, None)
        self.schedule_save()
        self.show_editor()

    def open_folder(self):
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(self.project_dir))).launch(self, None, None)


class App(Adw.Application):
    def __init__(self, project_dir):
        super().__init__(application_id=APP_ID)
        self.project_dir = project_dir

    def do_startup(self):
        Adw.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        window = self.props.active_window or Window(self, self.project_dir)
        window.present()


def run(project_dir):
    App(project_dir).run([])
