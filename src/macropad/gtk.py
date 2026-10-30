"""GTK 4 and libadwaita, with a helpful message if they're missing."""

import sys

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
except (ImportError, ValueError):
    sys.exit("This needs GTK 4 and libadwaita (python3-gi, gir1.2-adw-1): run `sudo make install`")

__all__ = ["Adw", "Gdk", "Gio", "GLib", "Gtk", "Pango"]
