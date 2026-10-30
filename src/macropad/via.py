"""Talk to the pad's firmware over VIA's raw HID channel.

VIA messages are 32 bytes; the reply echoes the command. 0xFF in the first
byte means the firmware didn't understand the command.
"""

import os
import select
from pathlib import Path

VENDOR_ID = 0xD010
PRODUCT_ID = 0x1601
# Raw HID interfaces start their report descriptor with usage page 0xFF60, usage 0x61.
RAW_HID_DESCRIPTOR = bytes([0x06, 0x60, 0xFF, 0x09, 0x61])

GET_PROTOCOL_VERSION = 0x01
GET_KEYCODE = 0x04
SET_KEYCODE = 0x05
GET_LAYER_COUNT = 0x11
GET_ENCODER = 0x14
SET_ENCODER = 0x15


class ViaError(Exception):
    pass


def find_hidraw():
    hid_id = f"HID_ID=0003:{VENDOR_ID:08X}:{PRODUCT_ID:08X}"
    for dev in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        if hid_id not in (dev / "device/uevent").read_text().splitlines():
            continue
        if (dev / "device/report_descriptor").read_bytes().startswith(RAW_HID_DESCRIPTOR):
            return Path("/dev") / dev.name
    raise ViaError("macropad not found (is it plugged in?)")


class Via:
    def __init__(self):
        path = find_hidraw()
        try:
            self.fd = os.open(path, os.O_RDWR)
        except PermissionError:
            raise ViaError(f"no permission to open {path}; run `sudo make install`") from None
        version = self._cmd(GET_PROTOCOL_VERSION)
        self.protocol = version[1] << 8 | version[2]
        if self.protocol < 0x0B:
            raise ViaError(f"VIA protocol {self.protocol} is too old (need 11+)")

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _cmd(self, *args):
        os.write(self.fd, bytes([0, *args]).ljust(33, b"\0"))  # leading 0 = report ID
        ready, _, _ = select.select([self.fd], [], [], 1)
        if not ready:
            raise ViaError("no reply from macropad")
        reply = os.read(self.fd, 32)
        if reply[0] != args[0]:
            raise ViaError(f"firmware rejected VIA command 0x{args[0]:02X}")
        return reply

    def layer_count(self):
        return self._cmd(GET_LAYER_COUNT)[1]

    def get_key(self, layer, row, col):
        r = self._cmd(GET_KEYCODE, layer, row, col)
        return r[4] << 8 | r[5]

    def set_key(self, layer, row, col, code):
        self._cmd(SET_KEYCODE, layer, row, col, code >> 8, code & 0xFF)

    def get_encoder(self, layer, index, clockwise):
        r = self._cmd(GET_ENCODER, layer, index, int(clockwise))
        return r[4] << 8 | r[5]

    def set_encoder(self, layer, index, clockwise, code):
        self._cmd(SET_ENCODER, layer, index, int(clockwise), code >> 8, code & 0xFF)
