"""Firefox profiles and their containers, read from Firefox's own files."""

import configparser
import json
from pathlib import Path

ROOTS = [
    Path("~/.mozilla/firefox"),
    Path("~/snap/firefox/common/.mozilla/firefox"),
    Path("~/.var/app/org.mozilla.firefox/.mozilla/firefox"),
]
# Firefox's built-in containers are stored without a name.
BUILT_IN = {1: "Personal", 2: "Work", 3: "Banking", 4: "Shopping"}


def profiles():
    """{name: folder} for every Firefox profile on this machine."""
    found = {}
    for root in ROOTS:
        root = root.expanduser()
        ini = configparser.ConfigParser(interpolation=None)
        if not ini.read(root / "profiles.ini"):
            continue
        for section in ini.values():
            if section.name.startswith("Profile") and "Path" in section:
                path = Path(section["Path"])
                if section.get("IsRelative", "1") == "1":
                    path = root / path
                found.setdefault(section.get("Name", path.name), path)
    return found


def containers(profile=None):
    """Container names in the named profile, or in every profile if it's None or missing."""
    all_profiles = profiles()
    folders = [all_profiles[profile]] if profile in all_profiles else all_profiles.values()
    names = []
    for folder in folders:
        try:
            identities = json.loads((folder / "containers.json").read_text())["identities"]
        except (OSError, ValueError, KeyError):
            continue
        for identity in identities:
            name = identity.get("name") or BUILT_IN.get(identity.get("userContextId"))
            if identity.get("public") and name and name not in names:
                names.append(name)
    return names
