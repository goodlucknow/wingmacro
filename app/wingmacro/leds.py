"""LED rendering: background < state colour < tap pulse < transients. 30 fps, diffs only."""
import asyncio
import logging
import math
import time

from .actions import FLOOR, level_path, mute_path
from .config import colour
from .pad import N_LEDS

log = logging.getLogger(__name__)

FLASH = (0, 0, 200)
OFF = (0, 0, 0)


class Leds:
    def __init__(self, cfg_ref, pad, wing, ctx):
        self.cfg, self.pad, self.wing, self.ctx = cfg_ref, pad, wing, ctx
        self.engine = None
        self.fx = {}  # idx -> (kind, t0, dur, colour)

    # --- transients (called by the engine) --------------------------------

    def transient(self, idx, kind, dur, mapping):
        if kind == "clear":
            self.fx.pop(idx, None)
            return
        target = colour(self._rule(mapping).get("on") if isinstance(self._rule(mapping), dict) else None,
                        (0, 0, 200))
        if kind == "confirm":
            dur = 0.45
        self.fx[idx] = (kind, time.monotonic(), dur, target)

    # --- rules -------------------------------------------------------------

    def _rule(self, m):
        """Explicit led rule, or one derived from the mapping's first action ('auto')."""
        r = m.get("led", "auto")
        if r != "auto":
            return r
        steps, _, _ = self.engine.resolve(m.get("do", []), None) if self.engine else ([], 0, 0)
        if not steps:
            return None
        s = steps[0]
        d = s.get("do")
        if d == "mute":
            return {"bind": f"mute:{s['target']}", "on": "red"}
        if d == "softmute":
            return {"bind": f"softmute:{s['target']}", "on": "red"}
        if d == "mgrp":
            return {"bind": f"mgrp:{s['n']}", "on": "red"}
        if d == "tap":
            return {"bind": "tap"}
        return None

    def paths(self):
        """WING paths the LED rules depend on, so the client learns their hashes."""
        out = set()
        for layer in self.cfg().get("layers", {}).values():
            for m in layer.get("buttons", {}).values():
                r = self._rule(m)
                if not isinstance(r, dict):
                    continue
                kind, _, arg = r.get("bind", "").partition(":")
                if kind in ("mute", "softmute"):
                    out.add(mute_path(arg)[0])
                if kind in ("floor", "softmute"):
                    out.add(level_path(arg))
                if kind == "mgrp":
                    out.add(f"/mgrp/{arg}/mute")
                if kind == "fx":
                    out.add("/fx/" + arg.split("==")[0])
        return out

    def _state(self, bind):
        kind, _, arg = bind.partition(":")
        w = self.wing
        if kind == "connected":
            return w.connected
        if kind == "mute":
            p, inv = mute_path(arg)
            v = w.cached(p)
            return None if v is None else bool(v) != inv
        if kind == "mgrp":
            v = w.cached(f"/mgrp/{arg}/mute")
            return None if v is None else bool(v)
        if kind == "floor":
            v = w.cached(level_path(arg))
            return None if v is None else v < FLOOR - 0.01
        if kind == "softmute":
            st = self.ctx.softmute.get(arg)
            if st and st.startswith("fading"):
                return "fading"
            if st:
                return st == "down"
            p, inv = mute_path(arg)
            m, lv = w.cached(p), w.cached(level_path(arg))
            return None if m is None else (bool(m) != inv)
        if kind == "fx":
            path, _, want = arg.partition("==")
            v = w.cached("/fx/" + path)
            return None if v is None else str(v) == want
        return None

    # --- frame -------------------------------------------------------------

    def frame(self, now):
        cfg = self.cfg()
        layer = self.engine.layer if self.engine else 0
        bg_default = colour(cfg.get("layers", {}).get(str(layer), {}).get("background"),
                            colour(cfg.get("pad", {}).get("background"), (22, 255, 47)))
        out = [bg_default] * N_LEDS
        maps = {}
        for idx in range(N_LEDS):
            wm = self.pad.key_wm(layer, idx) if self.pad.keymap else idx + 1
            if wm:
                _, m = self.engine.button_map(wm, layer)
                if m:
                    maps[m.get("led_index", idx)] = m
        for idx, m in maps.items():
            if not 0 <= idx < N_LEDS:
                continue
            bg = colour(m.get("background"), bg_default)
            c = bg
            r = self._rule(m)
            if isinstance(r, dict):
                if r.get("bind") == "tap":
                    c = self._tap(now, bg)
                else:
                    s = self._state(r.get("bind", ""))
                    if s == "fading":
                        a = colour(r.get("fading"), colour("amber"))
                        c = (a[0], a[1], int(a[2] * (0.55 + 0.45 * math.sin(now * 2 * math.pi * 1.5))))
                    elif s is True:
                        c = colour(r.get("on"), colour("red"))
                    elif s is False:
                        c = colour(r.get("off"), bg)
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

    def _tap(self, now, bg):
        taps, ms = self.ctx.taps, self.ctx.tap_ms
        if not taps or not ms:
            return bg
        period = ms / 1000
        since = (now - taps[-1]) % period
        return FLASH if since < 0.08 else bg

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(1 / 30)
            if not self.pad.connected or not self.engine:
                continue
            try:
                hsv = self.frame(time.monotonic())
                await loop.run_in_executor(None, self.pad.set_leds, hsv)
            except Exception as e:
                log.debug("led frame: %s", e)
