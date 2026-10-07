"""KB16 pad over Vial raw HID (protocol in docs/pad-map.md).

Uses hidapi. On Linux the PyPI `hidapi` wheel talks to the device through libusb, so it also
works in the IncusOS container (USB passthrough, no hidraw nodes), claiming interface 1 only.
"""
import asyncio
import logging
import threading
import time

import hid

log = logging.getLogger(__name__)

VID, PID, IFACE = 0xD010, 0x1601, 1
ROWS, COLS = 4, 5
QK_KB_0 = 0x7E00
KC_TRNS = 0x0001
N_LEDS = 16
ROW_CW, ROW_CCW = 253, 252
VIALRGB_DIRECT, VIALRGB_SOLID = 1, 2


class PadError(Exception):
    pass


class Pad:
    """Events come out of `self.events` (asyncio.Queue) as dicts:
    {"type": "key", "wm": 1..32, "pressed": bool, "layer": n, "row": r, "col": c}
    {"type": "layer", "layer": n}
    {"type": "connected"} / {"type": "disconnected"}
    """

    def __init__(self):
        self.dev = None
        self.connected = False
        self.layer = 0
        self.keymap = []  # [layer][row*COLS+col] -> keycode
        self.events = asyncio.Queue()
        self._loop = None
        self._wlock = threading.Lock()
        self._clock = threading.Lock()  # one cmd() waiting for a reply at a time
        self._reply = None
        self._reply_ev = threading.Event()
        self._seq = None
        self._leds_sent = [None] * N_LEDS
        self._saved_mode = None
        self._stop = threading.Event()

    # --- lifecycle --------------------------------------------------------

    async def run(self):
        """Connect, keep alive, reconnect on unplug. Runs until cancelled."""
        self._loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    await self._loop.run_in_executor(None, self._open)
                except PadError as e:
                    log.debug("pad: %s", e)
                    await asyncio.sleep(2)
                    continue
                self._emit({"type": "connected"})
                try:
                    while self.connected:
                        await self._loop.run_in_executor(None, self._hello)
                        await asyncio.sleep(1)
                except (OSError, ValueError, PadError) as e:
                    log.warning("pad lost: %s", e)
                self._drop()
                self._emit({"type": "disconnected"})
        finally:
            self.close()

    def close(self):
        """Restore the saved lighting mode and release the device."""
        if self.connected:
            try:
                self.unsubscribe()
                self.restore_lighting()
            except Exception:
                pass
        self._drop()

    def _open(self):
        paths = [d["path"] for d in hid.enumerate(VID, PID) if d["interface_number"] == IFACE]
        if not paths:
            raise PadError("KB16 not found")
        dev = hid.device()
        try:
            dev.open_path(paths[0])
        except OSError as e:
            raise PadError(f"open failed: {e}")
        self.dev = dev
        self._stop.clear()
        self.connected = True
        threading.Thread(target=self._reader, daemon=True).start()
        try:
            self._hello()
            self.keymap = self._read_keymap()
            r = self.cmd(0x08, 0x41)
            self._saved_mode = (r[2] | r[3] << 8, r[4], r[5], r[6], r[7])
            if self._saved_mode[0] == VIALRGB_DIRECT:  # left over from a crash
                self._saved_mode = None
            self.send(0x07, 0x41, VIALRGB_DIRECT & 0xFF, VIALRGB_DIRECT >> 8, 0, 0, 0, 0)
            self._leds_sent = [None] * N_LEDS
        except Exception:
            self._drop()
            raise
        log.info("pad connected, layer %d", self.layer)

    def _drop(self):
        self.connected = False
        self._stop.set()
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None

    # --- raw HID ----------------------------------------------------------

    def _write(self, data):
        if not self.dev:
            raise PadError("not connected")
        with self._wlock:
            if self.dev.write(b"\x00" + bytes(data).ljust(32, b"\0")) < 0:
                raise PadError("write failed")

    def send(self, *data):
        """Fire-and-forget command (its reply is discarded)."""
        self._write(data)

    def cmd(self, *data, timeout=1.0):
        with self._clock:
            self._reply_ev.clear()
            self._reply = (bytes(data[:2]), None)
            self._write(data)
            if not self._reply_ev.wait(timeout):
                raise PadError(f"no reply to {bytes(data[:2]).hex()}")
            return self._reply[1]

    def _reader(self):
        dev = self.dev
        while not self._stop.is_set():
            try:
                r = dev.read(32, 200)
            except (OSError, ValueError):
                if not self._stop.is_set():
                    self.connected = False
                return
            if not r:
                continue
            r = bytes(r)
            if r[0] == 0xF1:
                self._on_event(r)
            elif self._reply and r.startswith(self._reply[0]):
                self._reply = (self._reply[0], r)
                self._reply_ev.set()

    def _on_event(self, r):
        seq = r[8] if r[1] == 0x01 else r[3]
        if self._seq is not None and seq != (self._seq + 1) & 0xFF:
            log.warning("pad: dropped event(s), re-querying state")
            threading.Thread(target=self._hello, daemon=True).start()
        self._seq = seq
        if r[1] == 0x01:
            self.layer = r[4]
            self._emit({"type": "key", "wm": r[2], "pressed": bool(r[3]),
                        "layer": r[4], "row": r[5], "col": r[6]})
        elif r[1] == 0x02:
            self.layer = r[2]
            self._emit({"type": "layer", "layer": r[2]})

    def _emit(self, ev):
        if self._loop:
            self._loop.call_soon_threadsafe(self.events.put_nowait, ev)

    def _hello(self):
        r = self.cmd(0xF0, 0x01)
        if r[3] != self.layer:
            self.layer = r[3]
            self._emit({"type": "layer", "layer": r[3]})

    def unsubscribe(self):
        self.send(0xF0, 0x03)

    def _read_keymap(self):
        layers = self.cmd(0x11)[1]
        size = layers * ROWS * COLS * 2
        buf = b""
        while len(buf) < size:
            n = min(28, size - len(buf))
            buf += self.cmd(0x12, len(buf) >> 8, len(buf) & 0xFF, n)[4:4 + n]
        kcs = [int.from_bytes(buf[i:i + 2], "big") for i in range(0, size, 2)]
        per = ROWS * COLS
        return [kcs[l * per:(l + 1) * per] for l in range(layers)]

    # --- keymap helpers ---------------------------------------------------

    def key_wm(self, layer, index):
        """WM id at key index 0..15 on `layer` (following transparent keys down), or None."""
        row, col = divmod(index, 4)
        for l in range(min(layer, len(self.keymap) - 1), -1, -1):
            kc = self.keymap[l][row * COLS + col]
            if kc != KC_TRNS:
                return kc - QK_KB_0 + 1 if QK_KB_0 <= kc < QK_KB_0 + 32 else None
        return None

    # --- LEDs -------------------------------------------------------------

    def set_leds(self, hsv):
        """hsv: list of 16 (h, s, v). Sends only changed LEDs, up to 9 per report."""
        if not self.connected:
            return
        changed = [i for i in range(N_LEDS) if hsv[i] != self._leds_sent[i]]
        if not changed:
            return
        first, last = changed[0], changed[-1]
        i = first
        while i <= last:
            n = min(9, last - i + 1)
            data = [0x07, 0x42, i & 0xFF, i >> 8, n]
            for k in range(i, i + n):
                data += list(hsv[k])
            self.send(*data)
            i += n
        self._leds_sent = list(hsv)

    def restore_lighting(self):
        mode, speed, h, s, v = self._saved_mode or (VIALRGB_SOLID, 128, 22, 255, 47)
        self.send(0x07, 0x41, mode & 0xFF, mode >> 8, speed, h, s, v)
