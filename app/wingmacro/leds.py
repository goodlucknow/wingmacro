"""LED rendering, DiGiCo-macro style: each key has its own colour, changed only by `led` macro
actions (e.g. green in a toggle's On list, red in its Off list). Nothing is bound to console state.

Layers, lowest first: pad background < key colour (a toggle that is on: full brightness) < colour set
by `led` actions (with effect) < tap-tempo beat < press animations (charge, armed strobe, fire
animation, momentary glow). 30 fps (60 while animating); only changed LEDs are sent.
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
FULL = 200  # firmware brightness cap


def with_effect(c, effect, now):
    if effect == "flash":
        return c if int(now * 4) % 2 == 0 else OFF
    if effect == "pulse":  # slow breathing, ~0.5 Hz
        return (c[0], c[1], int(c[2] * (0.55 + 0.45 * math.sin(now * 2 * math.pi * 0.5))))
    return c


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _toward(base, target, k):
    """Brightness from `base` towards `target` by k (0..1), in the target's hue."""
    return (target[0], target[1], int(base[2] + (target[2] - base[2]) * k))


class Leds:
    def __init__(self, cfg_ref, pad, wing, ctx):
        self.cfg, self.pad, self.wing, self.ctx = cfg_ref, pad, wing, ctx
        self.engine = None
        self.fx = {}  # idx -> (kind, t0, dur, colour): per-key press animations
        self.blooms = {}  # idx -> [t0, colour, release time or None]
        self.last = [OFF] * N_LEDS  # latest frame, for the web UI preview
        self._fetching = {}  # console path -> last fetch attempt (tap keys reading the delay time)
        self._beating = False  # a tap key is flashing: render at 60 fps

    # --- colours ----------------------------------------------------------

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
        return (h, s, FULL) if v or s else FLASH  # a key set to off/black animates white

    def key_colour(self, layer, idx, wm, m, bg_default, now):
        """Resting colour of key `idx` whose mapping `m` lives on `layer`."""
        st = self.ctx.led_state.get((layer, idx))
        if st:
            c, effect = st
            return with_effect(colour(c, bg_default), effect, now)
        if m.get("mode") == "toggle" and self.engine and self.engine.toggles.get((layer, wm)):
            return self.anim_colour(m)  # a toggle that is on: full brightness
        return colour(m.get("background"), bg_default)

    # --- press animations (from the engine) -------------------------------

    def transient(self, idx, kind, dur, mapping):
        """progress: charge on key down (over the hold time, or briefly for other keys).
        armed: strobe through the cancel window. confirm: the fire animation (`fire_anim`: none
        fades the charge back, flash, bloom). held / release: a momentary key's glow (and bloom,
        held at its widest) while down, easing back on release."""
        now = time.monotonic()
        if kind == "clear":
            self.fx.pop(idx, None)
            return
        target = self.anim_colour(mapping)
        anim = mapping.get("fire_anim") or ("bloom" if mapping.get("mode") == "momentary"
                                            else "flash" if mapping.get("hold") else "none")
        if anim == "burst":  # old name
            anim = "bloom"
        if kind == "held":
            if anim == "bloom":
                self.blooms[idx] = [now, target, None]
            self.fx[idx] = ("held", now, None, target)
            return
        if kind == "release":
            if idx in self.blooms and self.blooms[idx][2] is None:
                self.blooms[idx][2] = now
            self.fx[idx] = ("fade", now, self.BLOOM_HALF, target)
            return
        if kind == "confirm":
            if anim == "bloom":
                self.blooms[idx] = [now, target, now + self.BLOOM_HALF]
                kind, dur = "glow", 2 * self.BLOOM_HALF  # the key stays lit while it blooms
            elif anim == "flash":
                dur = 0.75  # 3 flashes, 150 ms on / 150 ms off
            else:
                kind, dur = "fade", 0.3  # release the charge
        self.fx[idx] = (kind, now, dur, target)

    def _draw_fx(self, out, now):
        for idx, (kind, t0, dur, target) in list(self.fx.items()):
            e = now - t0
            if dur is not None and e > dur and kind != "progress":
                if kind != "armed":  # the engine ends armed (fire or cancel)
                    del self.fx[idx]
                continue
            if kind == "progress":  # charge: the key brightens towards full
                out[idx] = _toward(out[idx], target, min(e / dur, 1.0) if dur else 1.0)
            elif kind == "armed":  # strobe: short sharp blinks
                out[idx] = target if (e % 0.07) < 0.025 else OFF
            elif kind == "confirm":
                out[idx] = target if int(e / 0.15) % 2 == 0 else OFF
            elif kind == "held":
                out[idx] = target
            elif kind == "glow":  # full, easing back at the end
                out[idx] = _toward(out[idx], target, 1 - _smooth((e - (dur - 0.15)) / 0.15))
            elif kind == "fade":  # from full back to the key's resting colour
                out[idx] = _toward(out[idx], target, 1 - _smooth(e / dur))

    # Bloom: light swells out of the key into its neighbours and shrinks back into it. A fire
    # animation grows for BLOOM_HALF and shrinks straight back; a momentary key holds it at its
    # widest while down and shrinks on release.
    BLOOM_HALF = 0.4      # seconds to grow (and to shrink)
    BLOOM_RADIUS = 1.5    # keys at its widest: neighbours fully, diagonals partly, nothing much further
    BLOOM_EDGE = 1.1      # soft edge, in keys
    BLOOM_FALLOFF = 0.3   # dimmer with distance: neighbours ~80%, diagonals ~70%

    def bloom_radius(self, t0, release, now):
        """Radius in keys, or None once fully shrunk."""
        grow = lambda t: self.BLOOM_RADIUS * math.sin(math.pi / 2 * min(max(t, 0) / self.BLOOM_HALF, 1))
        if release is None or now < release:
            return grow(now - t0)
        f = (now - release) / self.BLOOM_HALF
        return None if f >= 1 else grow(release - t0) * math.cos(math.pi / 2 * f)

    def level_at(self, d, r):
        k = _smooth(1 - (d - r) / self.BLOOM_EDGE) * (1 - self.BLOOM_FALLOFF * min(d, 2) / 1.5)
        return k * k  # LED brightness is linear, the eye isn't

    def bloom_level(self, d, e):
        """0..1 brightness of a key `d` keys from a fire-animation bloom, `e` seconds after firing."""
        r = self.bloom_radius(0.0, self.BLOOM_HALF, e)
        return 0.0 if r is None or e < 0 else self.level_at(d, r)

    def _draw_blooms(self, out, now):
        for src, (t0, c, release) in list(self.blooms.items()):
            r = self.bloom_radius(t0, release, now)
            if r is None:
                del self.blooms[src]
                continue
            sy, sx = divmod(src, 4)
            for idx in range(N_LEDS):
                if idx == src:
                    continue
                y, x = divmod(idx, 4)
                k = self.level_at(math.hypot(x - sx, y - sy), r)
                if c[2] * k > out[idx][2]:  # takes over once brighter than the key's own colour
                    out[idx] = (c[0], c[1], int(c[2] * k))

    # --- tap tempo ----------------------------------------------------------

    def tap_period(self, step, now):
        """(period s, phase origin) for a tap key: the tapped tempo, else the first slot's delay time
        on the console (fetched once, then kept current by change events)."""
        slots = sorted(int(x) for x in step.get("slots", []))
        st = self.ctx.taps.get(tuple(slots))
        if st and st["ms"]:
            return st["ms"] / 1000, st["t"][-1]
        for slot in slots:
            path = f"/fx/{slot}/time"
            ms = self.wing.cached(path) if self.wing else None
            if isinstance(ms, (int, float)) and ms > 0:
                return ms / 1000, 0.0
            if self.wing and self.wing.connected and now - self._fetching.get(path, -99) > 5:
                self._fetching[path] = now
                asyncio.get_running_loop().create_task(self.wing.value(path))
        return None, 0.0

    TAP_PEAK = 0.03  # s at full brightness on each beat: a hard attack
    AFTER_TAP_BEATS = 8  # `beat_flash: after_tap`: flash this many beats after the last tap, then rest

    def _tap(self, now, c, step, m):
        """Beat flash: hard attack (full for TAP_PEAK), then a quick smooth decay."""
        period, origin = self.tap_period(step, now)
        if not period:
            return c
        if m.get("beat_flash") == "after_tap":  # only the first AFTER_TAP_BEATS beats after tapping
            tapped = self.ctx.taps.get(tuple(sorted(int(x) for x in step.get("slots", []))))
            if not tapped or not tapped["ms"] or now - tapped["t"][-1] >= self.AFTER_TAP_BEATS * period:
                return c
        since = (now - origin) % period
        k = 1.0 if since < self.TAP_PEAK else math.exp(-(since - self.TAP_PEAK) / min(0.06, period / 8))
        return _toward(c, self.anim_colour(m), k) if k > 0.02 else c

    # --- frame ----------------------------------------------------------------

    def frame(self, now):
        layer = self.engine.layer if self.engine else 0
        bg_default = self.pad_background(layer)
        out = [bg_default] * N_LEDS
        self._beating = False
        for idx in range(N_LEDS):
            wm = self.pad.key_wm(layer, idx) if self.pad.keymap else idx + 1
            if not wm:
                continue
            l, m = self.engine.button_map(wm, layer)
            if not m:
                continue
            c = self.key_colour(l, idx, wm, m, bg_default, now)
            steps = self.engine.expand(m.get("do") or [])
            if steps and steps[0].get("do") == "tap":
                c = self._tap(now, c, steps[0], m)
                self._beating = True
            out[idx] = c
        self._draw_fx(out, now)
        self._draw_blooms(out, now)
        return out

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(1 / 60 if self.blooms or self.fx or self._beating else 1 / 30)  # smoother while animating
            if not self.engine:
                continue
            try:
                hsv = self.last = self.frame(time.monotonic())
                if self.pad.connected:
                    await loop.run_in_executor(None, self.pad.set_leds, hsv)
            except Exception as e:
                log.debug("led frame: %s", e)
