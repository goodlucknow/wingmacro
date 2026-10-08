"""LED rendering, DiGiCo-macro style: each key has its own colour, changed only by `led` macro
actions (e.g. green in a toggle's A side, red in its B side). Nothing is bound to console state.

Layers, lowest first: pad background < key colour < colour set by `led` actions (with effect)
< tap-tempo beat flash < hold/confirm transients. 30 fps, only changed LEDs are sent.
"""
import asyncio
import logging
import math
import time

from .config import colour
from .pad import N_LEDS

log = logging.getLogger(__name__)

FLASH = (0, 0, 200)
OFF = (0, 0, 0)


def with_effect(c, effect, now):
    if effect == "flash":
        return c if int(now * 4) % 2 == 0 else OFF
    if effect == "pulse":
        return (c[0], c[1], int(c[2] * (0.55 + 0.45 * math.sin(now * 2 * math.pi * 1.2))))
    return c


class Leds:
    def __init__(self, cfg_ref, pad, wing, ctx):
        self.cfg, self.pad, self.wing, self.ctx = cfg_ref, pad, wing, ctx
        self.engine = None
        self.fx = {}  # idx -> (kind, t0, dur, colour)
        self.last = [OFF] * N_LEDS  # latest frame, for the web UI preview
        self.blooms = []  # (source idx, t0, colour): glow spreading out of a key and back in

    def pad_background(self, layer=None):
        cfg = self.cfg()
        layer = (self.engine.layer if self.engine else 0) if layer is None else layer
        return colour(cfg.get("layers", {}).get(str(layer), {}).get("background"),
                      colour(cfg.get("pad", {}).get("background"), (22, 255, 47)))

    def anim_colour(self, mapping):
        """`hold_colour`, or by default the key's own colour (else the pad background) at full brightness."""
        if mapping.get("hold_colour") is not None:
            return colour(mapping["hold_colour"], FLASH)
        h, s, v = colour(mapping.get("background"), self.pad_background())
        return (h, s, 200) if v or s else FLASH  # a key set to off/black animates white

    def transient(self, idx, kind, dur, mapping):
        """Feedback from the engine: hold progress fill, armed flash, and the fire animation
        (`fire_anim`: none | flash | bloom; hold keys default to flash, others to none).
        All use anim_colour()."""
        if kind == "clear":
            self.fx.pop(idx, None)
            return
        target = self.anim_colour(mapping)
        now = time.monotonic()
        if kind == "confirm":
            anim = mapping.get("fire_anim", "flash" if mapping.get("hold") else "none")
            if anim == "none":
                self.fx.pop(idx, None)
                return
            if anim in ("bloom", "burst"):  # "burst" was the old name
                self.blooms.append((idx, now, target))
                kind, dur = "glow", self.BLOOM_TIME  # the key itself stays lit while it blooms
            else:
                dur = 0.75  # 3 flashes, 150 ms on / 150 ms off
        self.fx[idx] = (kind, now, dur, target)

    def key_colour(self, layer, idx, m, bg_default, now):
        """Resting colour of key `idx` whose mapping `m` lives on `layer`."""
        st = self.ctx.led_state.get((layer, idx))
        if st:
            c, effect = st
            return with_effect(colour(c, bg_default), effect, now)
        return colour(m.get("background"), bg_default)

    def frame(self, now):
        layer = self.engine.layer if self.engine else 0
        bg_default = self.pad_background(layer)
        out = [bg_default] * N_LEDS
        for idx in range(N_LEDS):
            wm = self.pad.key_wm(layer, idx) if self.pad.keymap else idx + 1
            if not wm:
                continue
            l, m = self.engine.button_map(wm, layer)
            if not m:
                continue
            c = self.key_colour(l, idx, m, bg_default, now)
            steps = self.engine.expand(m.get("do") or [])
            if steps and steps[0].get("do") == "tap":
                c = self._tap(now, c, steps[0])
            out[idx] = c
        for idx, (kind, t0, dur, target) in list(self.fx.items()):
            e = now - t0
            if kind == "progress":
                f = min(e / dur, 1.0) if dur else 1.0
                out[idx] = (target[0], target[1], int(out[idx][2] + (target[2] - out[idx][2]) * f))
            elif kind == "armed":
                if e > dur:
                    continue  # engine clears/confirms
                out[idx] = target if int(e * 12) % 2 == 0 else OFF
            elif kind == "confirm":
                if e > dur:
                    del self.fx[idx]
                    continue
                out[idx] = target if int(e / 0.15) % 2 == 0 else OFF
            elif kind == "glow":
                if e > dur:
                    del self.fx[idx]
                    continue
                k = 1 - self._smooth((e - (dur - 0.15)) / 0.15)  # eases back to the key's colour at the end
                out[idx] = (target[0], target[1], int(out[idx][2] + (target[2] - out[idx][2]) * k))
        self._draw_blooms(out, now)
        return out

    # Bloom: light swells out of the pressed key into its neighbours and shrinks back into it.
    # The radius rises and falls over BLOOM_TIME; keys inside it light, with a soft edge.
    BLOOM_TIME = 0.8    # seconds, out and back
    BLOOM_RADIUS = 1.5  # keys at its widest: neighbours fully, diagonals partly, nothing much further
    BLOOM_EDGE = 1.1    # soft edge, in keys
    BLOOM_FALLOFF = 0.3 # dimmer with distance: neighbours ~80%, diagonals ~70%

    @staticmethod
    def _smooth(x):
        x = min(1.0, max(0.0, x))
        return x * x * (3 - 2 * x)

    def bloom_level(self, d, e):
        """0..1 brightness of a key `d` keys from the source, `e` seconds after firing."""
        if not 0 <= e < self.BLOOM_TIME:
            return 0.0
        r = self.BLOOM_RADIUS * math.sin(math.pi * e / self.BLOOM_TIME)  # out, then back in
        k = self._smooth(1 - (d - r) / self.BLOOM_EDGE) * (1 - self.BLOOM_FALLOFF * min(d, 2) / 1.5)
        return k * k  # LED brightness is linear, the eye isn't

    def _draw_blooms(self, out, now):
        self.blooms = [b for b in self.blooms if now - b[1] < self.BLOOM_TIME]
        for src, t0, c in self.blooms:
            e = now - t0
            sy, sx = divmod(src, 4)
            for idx in range(N_LEDS):
                if idx == src:
                    continue
                y, x = divmod(idx, 4)
                k = self.bloom_level(math.hypot(x - sx, y - sy), e)
                if c[2] * k > out[idx][2]:  # takes over once brighter than the key's own colour
                    out[idx] = (c[0], c[1], int(c[2] * k))

    def _tap(self, now, c, step):
        st = self.ctx.taps.get(tuple(sorted(int(x) for x in step.get("slots", []))))
        if not st or not st["ms"]:
            return c
        since = (now - st["t"][-1]) % (st["ms"] / 1000)
        return FLASH if since < 0.08 else c

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(1 / 60 if self.blooms or self.fx else 1 / 30)  # smoother while animating
            if not self.engine:
                continue
            try:
                hsv = self.last = self.frame(time.monotonic())
                if self.pad.connected:
                    await loop.run_in_executor(None, self.pad.set_leds, hsv)
            except Exception as e:
                log.debug("led frame: %s", e)
