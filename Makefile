# sudo make install    set up this machine (safe to re-run, e.g. after moving the folder)
# sudo make uninstall  undo it (the keymap stays on the pad)
# make push            write keymap.py to the pad
# make pull            print the pad's current keymap
# make logs            watch key presses and errors
# make gui             set up shortcuts in a window (also in the app menu)
# make note            open the quick note window

DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# Under sudo, the uv and systemd steps still run as the desktop user.
USER_NAME := $(or $(SUDO_USER),$(shell id -un))
USER_HOME := $(shell getent passwd $(USER_NAME) | cut -d: -f6)
USER_ID := $(shell id -u $(USER_NAME))
ifeq ($(shell id -u),0)
SUDO :=
AS_USER := sudo -u $(USER_NAME) -H env XDG_RUNTIME_DIR=/run/user/$(USER_ID) \
	DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(USER_ID)/bus
else
SUDO := sudo
AS_USER :=
endif

UV := $(or $(shell command -v uv),$(wildcard $(USER_HOME)/.local/bin/uv),$(wildcard $(USER_HOME)/.cargo/bin/uv))
UNIT := $(USER_HOME)/.config/systemd/user/macropad.service
RULE := /etc/udev/rules.d/70-macropad.rules
DESKTOP := $(USER_HOME)/.local/share/applications/uk.co.symroe.Macropad.desktop
# The GUI uses Ubuntu's GTK bindings, so the venv is built on the system
# Python with access to its packages (PyGObject from PyPI needs compiling).
SYSTEM_PYTHON := /usr/bin/python3
APT_PACKAGES := python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

.PHONY: install uninstall push pull logs gui note check-user venv

install: check-user
	dpkg -s $(APT_PACKAGES) >/dev/null 2>&1 || $(SUDO) apt-get install -y $(APT_PACKAGES)
	$(MAKE) --no-print-directory venv
	$(SUDO) install -m 644 $(DIR)/udev/70-macropad.rules $(RULE)
	$(SUDO) udevadm control --reload
	$(SUDO) udevadm trigger --subsystem-match=input --subsystem-match=hidraw --subsystem-match=misc
	$(AS_USER) mkdir -p $(dir $(UNIT))
	sed 's|@DIR@|$(DIR)|g' $(DIR)/systemd/macropad.service.in | $(AS_USER) tee $(UNIT) >/dev/null
	$(AS_USER) systemctl --user daemon-reload
	$(AS_USER) systemctl --user enable macropad.service
	$(AS_USER) systemctl --user restart macropad.service
	$(AS_USER) mkdir -p $(dir $(DESKTOP))
	sed 's|@DIR@|$(DIR)|g' $(DIR)/desktop/macropad.desktop.in | $(AS_USER) tee $(DESKTOP) >/dev/null
	@echo "Done. Now run: make push"

uninstall: check-user
	-$(AS_USER) systemctl --user disable --now macropad.service
	$(AS_USER) rm -f $(UNIT) $(DESKTOP)
	$(AS_USER) systemctl --user daemon-reload
	$(SUDO) rm -f $(RULE)
	$(SUDO) udevadm control --reload

check-user:
	@if [ "$(USER_NAME)" = root ]; then echo "Run as your normal user (with or without sudo), not as root." >&2; exit 1; fi
	@if [ -z "$(UV)" ]; then echo "uv is needed: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; fi

venv:
	grep -qs 'include-system-site-packages = true' $(DIR)/.venv/pyvenv.cfg || \
		$(AS_USER) $(UV) venv --clear --system-site-packages --python $(SYSTEM_PYTHON) $(DIR)/.venv
	$(AS_USER) $(UV) sync --project $(DIR)

push pull gui note:
	cd $(DIR) && $(AS_USER) $(UV) run macropad $@

logs:
	$(AS_USER) journalctl --user -fu macropad
