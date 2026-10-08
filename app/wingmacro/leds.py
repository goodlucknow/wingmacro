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
        self.bursts = []  # (source idx, t0, colour): rings radiating across the pad

    def transient(self, idx, kind, dur, mapping):
        """Feedback from the engine: hold progress fill, armed flash, and the fire animation
        (`fire_anim`: none | flash | burst; hold keys default to flash, others to none).
        All use the mapping's `hold_colour` (default white)."""
        if kind == "clear":
            self.fx.pop(idx, None)
            return
        target = colour(mapping.get("hold_colour"), FLASH)
        now = time.monotonic()
        if kind == "confirm":  # 3 flashes, 150 ms on / 150 ms off
            anim = mapping.get("fire_anim", "flash" if mapping.get("hold") else "none")
            if anim == "none":
                self.fx.pop(idx, None)
                return
            dur = 0.75
            if anim == "burst":
                self.bursts.append((idx, now, target))
        self.fx[idx] = (kind, now, dur, target)

    def key_colour(self, layer, idx, m, bg_default, now):
        """Resting colour of key `idx` whose mapping `m` lives on `layer`."""
        st = self.ctx.led_state.get((layer, idx))
        if st:
            c, effect = st
            return with_effect(colour(c, bg_default), effect, now)
        return colour(m.get("background"), bg_default)

    def frame(self, now):
        cfg = self.cfg()
        layer = self.engine.layer if self.engine else 0
        bg_default = colour(cfg.get("layers", {}).get(str(layer), {}).get("background"),
                            colour(cfg.get("pad", {}).get("background"), (22, 255, 47)))
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
        self._draw_bursts(out, now)
        return out

    # Burst, after QMK's SOLID_SPLASH (quantum/rgb_matrix/animations/solid_splash_anim.h): a wavefront
    # spreads from the key; each key lights as the front reaches it, then fades out behind it.
    BURST_TIME = 1.0   # whole animation, seconds
    BURST_SPEED = 7.0  # keys per second: the front crosses the pad in ~0.6 s
    BURST_FADE = 0.38  # seconds each key takes to fade after the front passes
    BURST_EDGE = 0.9   # soft leading edge, in keys
    BURST_FAR = 0.4    # strength at the far corner (4.24 keys away), relative to the neighbours

    @staticmethod
    def _smooth(x):
        x = min(1.0, max(0.0, x))
        return x * x * (3 - 2 * x)

    def burst_level(self, d, e):
        """0..1 brightness of a key `d` keys from the source, `e` seconds after firing."""
        sm = self._smooth
        lag = e - d / self.BURST_SPEED                      # seconds since the front reached this key
        lead = sm(1 + lag * self.BURST_SPEED / self.BURST_EDGE)   # eases in just ahead of the front
        tail = 1 - sm(lag / self.BURST_FADE)                 # eases out behind it
        reach = 1 - (1 - self.BURST_FAR) * min(d / 4.24, 1)  # weaker the further it travels, never zero
        end = 1 - sm((e - (self.BURST_TIME - 0.1)) / 0.1)    # everything gone by BURST_TIME
        k = lead * tail * end
        return k * k * reach  # squared envelope: LED brightness is linear, the eye isn't

    def _draw_bursts(self, out, now):
        self.bursts = [b for b in self.bursts if now - b[1] < self.BURST_TIME]
        for src, t0, c in self.bursts:
            e = now - t0
            sy, sx = divmod(src, 4)
            for idx in range(N_LEDS):
                if idx == src:
                    continue
                y, x = divmod(idx, 4)
                k = self.burst_level(math.hypot(x - sx, y - sy), e)
                if k > 0.01 and c[2] * k > out[idx][2]:
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
            await asyncio.sleep(1 / 60 if self.bursts or self.fx else 1 / 30)  # smoother while animating
            if not self.engine:
                continue
            try:
                hsv = self.last = self.frame(time.monotonic())
                if self.pad.connected:
                    await loop.run_in_executor(None, self.pad.set_leds, hsv)
            except Exception as e:
                log.debug("led frame: %s", e)
