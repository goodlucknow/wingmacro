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

    def transient(self, idx, kind, dur, mapping):
        """Hold feedback from the engine: progress fill, armed flash, confirm flash."""
        if kind == "clear":
            self.fx.pop(idx, None)
            return
        if kind == "confirm":
            dur = 0.45
        self.fx[idx] = (kind, time.monotonic(), dur, FLASH)

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
            steps, _, _ = self.engine.resolve(m.get("do", []), None)
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
                out[idx] = FLASH if int(e * 12) % 2 == 0 else OFF
            elif kind == "confirm":
                if e > dur:
                    del self.fx[idx]
                    continue
                out[idx] = target if int(e / 0.075) % 2 == 0 else OFF
        return out

    def _tap(self, now, c, step):
        st = self.ctx.taps.get(tuple(sorted(int(x) for x in step.get("slots", []))))
        if not st or not st["ms"]:
            return c
        since = (now - st["t"][-1]) % (st["ms"] / 1000)
        return FLASH if since < 0.08 else c

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(1 / 30)
            if not self.engine:
                continue
            try:
                hsv = self.last = self.frame(time.monotonic())
                if self.pad.connected:
                    await loop.run_in_executor(None, self.pad.set_leds, hsv)
            except Exception as e:
                log.debug("led frame: %s", e)
