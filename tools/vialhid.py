#!/usr/bin/env python3
"""Talk to the KB16's Vial raw-HID interface over libusb (no hidraw needed).

Usage: tools/vialhid.py dump      # print keymap + encoder map for all layers

Detaches the kernel driver from interface 1 only (keyboard/mouse interfaces stay
with the OS) and reattaches it on exit.
"""
import sys

import usb.core
import usb.util

VID, PID = 0xD010, 0x1601
IFACE, EP_IN, EP_OUT = 1, 0x82, 0x03
ROWS, COLS, ENCODERS = 4, 5, 3
MIDI_NOTE_BASE = 48  # MI_C with default octave


class Vial:
    def __enter__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            sys.exit("KB16 not found")
        self.reattach = self.dev.is_kernel_driver_active(IFACE)
        if self.reattach:
            self.dev.detach_kernel_driver(IFACE)
        usb.util.claim_interface(self.dev, IFACE)
        return self

    def __exit__(self, *exc):
        usb.util.release_interface(self.dev, IFACE)
        if self.reattach:
            self.dev.attach_kernel_driver(IFACE)

    def cmd(self, *data):
        self.dev.write(EP_OUT, bytes(data).ljust(32, b"\0"), timeout=1000)
        return bytes(self.dev.read(EP_IN, 32, timeout=1000))

    def layer_count(self):
        return self.cmd(0x11)[1]

    def keymap(self, layers):
        size = layers * ROWS * COLS * 2
        buf = b""
        while len(buf) < size:
            n = min(28, size - len(buf))
            buf += self.cmd(0x12, len(buf) >> 8, len(buf) & 0xFF, n)[4 : 4 + n]
        kcs = [int.from_bytes(buf[i : i + 2], "big") for i in range(0, size, 2)]
        per = ROWS * COLS
        return [kcs[l * per : (l + 1) * per] for l in range(layers)]

    def encoder(self, layer, idx):
        r = self.cmd(0xFE, 0x03, layer, idx)
        return int.from_bytes(r[0:2], "big"), int.from_bytes(r[2:4], "big")


def name(kc):
    if kc == 0x0000:
        return "--"
    if kc == 0x0001:
        return "▽"
    if 0x5200 <= kc < 0x5220:
        return f"TO({kc & 0x1F})"
    if 0x5220 <= kc < 0x5240:
        return f"MO({kc & 0x1F})"
    if 0x7103 <= kc < 0x7103 + 72:
        return f"n{MIDI_NOTE_BASE + kc - 0x7103}"
    return {0xD9: "WhUp", 0xDA: "WhDn"}.get(kc, f"0x{kc:04X}")


def dump():
    with Vial() as v:
        layers = v.layer_count()
        for l, keys in enumerate(v.keymap(layers)):
            print(f"layer {l}")
            for r in range(ROWS):
                print("  " + " ".join(f"{name(k):>7}" for k in keys[r * COLS : (r + 1) * COLS]))
            encs = [v.encoder(l, e) for e in range(ENCODERS)]
            print("  enc  " + "  ".join(f"{name(a)}/{name(b)}" for a, b in encs))


if __name__ == "__main__":
    {"dump": dump}[sys.argv[1] if len(sys.argv) > 1 else "dump"]()
