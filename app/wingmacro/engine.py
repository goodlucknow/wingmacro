"""Pad events -> mappings -> macros. See docs/config-model.md."""
import asyncio
import copy
import logging
import time

from .actions import ACTIONS, ROTARY

log = logging.getLogger(__name__)

PUSH_POS = {(0, 4): "left", (1, 4): "right"}
KNOBS = ["left", "right"]
ROW_CW, ROW_CCW = 253, 252
# (max seconds between ticks, step multiplier); slower than all thresholds = 1 step per tick
ACCEL = {
    "off": [],
    "fine": [(0.03, 4), (0.06, 2)],
    "normal": [(0.02, 10), (0.04, 5), (0.08, 2)],
}


class Recorder:
    """Wraps the WING client for a momentary press: remembers each path's value before its
    first write, so the release can put everything back."""

    def __init__(self, wing, record):
        self._w, self._rec = wing, record

    def __getattr__(self, name):
        return getattr(self._w, name)

    async def set(self, path, value):
        if path not in self._rec:
            self._rec[path] = await self._w.value(path)
        return await self._w.set(path, value)


class Engine:
    def __init__(self, cfg_ref, ctx, leds=None):
        self.cfg = cfg_ref
        self.ctx = ctx
        self.leds = leds
        self.layer = 0
        self.buttons = {}  # wm -> state
        self.knobs = {k: {"held": False, "turned": False, "t": 0.0, "dir": 0} for k in KNOBS}
        self.toggles = {}  # (mapping layer, wm or "push:<knob>") -> True while a toggle key is on
        self.running = {}  # macro key -> task
        self.log = []  # recent events for the web UI

    # --- lookup -----------------------------------------------------------

    def _lookup(self, kind, key, layer=None):
        layers = self.cfg().get("layers", {})
        for l in range((self.layer if layer is None else layer), -1, -1):
            m = layers.get(str(l), {}).get(kind, {}).get(str(key))
            if m:
                return l, m
        return None, None

    def button_map(self, wm, layer=None):
        return self._lookup("buttons", wm, layer)

    def encoder_map(self, knob, layer=None):
        return self._lookup("encoders", knob, layer)

    def steps_for(self, m, key, advance=False):
        """Steps a button / knob-push mapping runs now. A toggle mapping keeps its own on/off state
        (deliberately not read from the console) and runs its On list, then its Off list."""
        on_steps = m.get("do") or []
        if not m.get("toggle"):
            return on_steps
        on = self.toggles.get(key, False)
        if advance:
            self.toggles[key] = not on
        if not on:
            return on_steps
        return m.get("off") or []

    def expand(self, steps, depth=0):
        """Steps with `macro` calls inlined (for inspection; running expands lazily)."""
        out = []
        for st in steps:
            if st.get("do") == "macro" and depth < 8:
                out += self.expand(self.cfg().get("macros", {}).get(st.get("name"), {}).get("steps", []), depth + 1)
            else:
                out.append(st)
        return out

    # --- events -----------------------------------------------------------

    async def handle(self, ev):
        t = ev["type"]
        if t == "layer":
            self.layer = ev["layer"]
        elif t == "key":
            self.layer = ev["layer"]
            self._log(ev)
            row, col = ev["row"], ev["col"]
            if row in (ROW_CW, ROW_CCW):
                if col < len(KNOBS):
                    await self.turn(KNOBS[col], 1 if row == ROW_CW else -1)
            elif (row, col) in PUSH_POS:
                self.push(PUSH_POS[(row, col)], ev["pressed"])
            else:
                idx = row * 4 + col if row < 4 and col < 4 else None
                (self.press if ev["pressed"] else self.release)(ev["wm"], idx)
        elif t == "disconnected":
            for st in self.buttons.values():
                if st.get("timer"):
                    st["timer"].cancel()
                if st["phase"] == "held":
                    asyncio.create_task(self._momentary_end(st))
            self.buttons.clear()

    def _log(self, ev):
        self.log = (self.log + [dict(ev, t=time.time())])[-50:]

    # --- buttons ----------------------------------------------------------

    def press(self, wm, idx):
        st = self.buttons.get(wm)
        if st and st["phase"] == "armed":  # tap after a hold's release cancels it
            st["timer"].cancel()
            st["phase"] = "cancelling"
            self._led(st, "clear")
            log.info("WM%d hold cancelled", wm)
            return
        l, m = self.button_map(wm)
        if not m:
            return
        pad = self.cfg().get("pad", {})
        st = {"phase": "pressed", "map": m, "layer": l, "wm": wm,
              "idx": m.get("led_index", idx), "t0": time.monotonic()}
        if m.get("trigger", "press") == "momentary":
            self._led(st, "confirm")
            self._momentary_start(st)
        elif m.get("trigger", "press") == "hold":
            st["phase"] = "holding"
            st["hold"] = m.get("hold_ms", pad.get("hold_ms", 800)) / 1000
            self._led(st, "progress", st["hold"])
        self.buttons[wm] = st

    def release(self, wm, idx):
        st = self.buttons.get(wm)
        if not st:
            return
        if st["phase"] == "pressed":
            del self.buttons[wm]
            self.fire(st)
        elif st["phase"] == "held":
            del self.buttons[wm]
            asyncio.create_task(self._momentary_end(st))
        elif st["phase"] == "cancelling":
            del self.buttons[wm]
        elif st["phase"] == "holding":
            if time.monotonic() - st["t0"] >= st["hold"]:
                cancel = st["map"].get("cancel_ms", self.cfg().get("pad", {}).get("cancel_ms", 400)) / 1000
                st["phase"] = "armed"
                st["timer"] = asyncio.get_running_loop().call_later(cancel, self._armed_fire, wm)
                self._led(st, "armed", cancel)
            else:
                del self.buttons[wm]
                self._led(st, "clear")

    def _armed_fire(self, wm):
        st = self.buttons.pop(wm, None)
        if st:
            self._led(st, "confirm")
            self.fire(st)

    def fire(self, st):
        if st["map"].get("trigger", "press") != "hold":  # hold keys animate in _armed_fire
            self._led(st, "confirm")
        key = (st["layer"], st["wm"])
        self.run(self.steps_for(st["map"], key, advance=True), key, t0=st["t0"], src=self._src(st))

    @staticmethod
    def _src(st):
        """LED address of the key that fired: (mapping layer, key index)."""
        return (st["layer"], st["idx"]) if st.get("idx") is not None else None

    def _momentary_start(self, st):
        """Run on key down. Steps run against a Recorder so the release can restore."""
        st["phase"] = "held"
        st["record"] = {}
        steps = st["map"].get("do") or []
        st["steps"] = self.expand(steps)
        ctx = copy.copy(self.ctx)
        ctx.wing = Recorder(self.ctx.wing, st["record"])
        ctx.led_record = st["led_record"] = {}
        st["task"] = asyncio.create_task(
            self._run(steps, ("momentary", st["layer"], st["wm"]), st["t0"], self._src(st), ctx))

    async def _momentary_end(self, st):
        """On release: stop the macro, restore what it changed, fade faders back."""
        task = st["task"]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for key, prev in st["led_record"].items():
            if prev is None:
                self.ctx.led_state.pop(key, None)
            else:
                self.ctx.led_state[key] = prev
        w = self.ctx.wing
        for path, value in st["record"].items():
            if value is not None:
                await w.set(path, value)
        for s in reversed(st["steps"]):
            if s.get("do") == "fade" and s.get("db") != "back":
                await ACTIONS["fade"](self.ctx, dict(s, db="back", wait=False))

    # --- testing from the UI --------------------------------------------------

    def test_steps(self, steps, src=None):
        """Run actions straight away (the UI's run buttons). `src` = (layer, key index) for LED actions."""
        self.run(steps, ("test", id(steps)), src=tuple(src) if src else None)

    def test_key(self, layer, wm, idx):
        """Act as if the key were pressed: toggle state, LED animations and all. Hold keys fire at once;
        momentary keys are held for a second."""
        l, m = self.button_map(wm, layer)
        if not m:
            raise ValueError(f"WM{wm} isn't mapped on layer {layer + 1}")
        st = {"phase": "pressed", "map": m, "layer": l, "wm": wm, "idx": m.get("led_index", idx), "t0": time.monotonic()}
        if m.get("trigger") == "momentary":
            self._led(st, "confirm")
            self._momentary_start(st)
            asyncio.get_running_loop().call_later(1.0, lambda: asyncio.create_task(self._momentary_end(st)))
        elif m.get("trigger") == "hold":
            self._led(st, "confirm")
            self.fire(st)
        else:
            self.fire(st)

    def _led(self, st, kind, dur=None):
        if self.leds and st.get("idx") is not None:
            self.leds.transient(st["idx"], kind, dur, st["map"])

    # --- macros -----------------------------------------------------------

    def run(self, steps, key, retrigger="restart", t0=None, src=None):
        old = self.running.get(key)
        if old and not old.done():
            if retrigger == "ignore":
                return
            if retrigger == "restart":
                old.cancel()
        task = asyncio.create_task(self._run(steps, key, t0, src))
        if retrigger != "parallel":
            self.running[key] = task

    async def _run(self, steps, key, t0=None, src=None, ctx=None):
        try:
            await self._steps(steps, t0, src, ctx, 0)
        finally:
            if self.running.get(key) is asyncio.current_task():
                del self.running[key]

    async def _steps(self, steps, t0, src, ctx, depth):
        for st in steps:
            if st.get("do") == "macro":  # run a shared macro inline
                if depth >= 8:
                    log.warning("macro %r: nested too deep", st.get("name"))
                    continue
                m = self.cfg().get("macros", {}).get(st.get("name"))
                if m is None:
                    log.warning("macro %r not found", st.get("name"))
                    continue
                await self._steps(m.get("steps", []), t0, src, ctx, depth + 1)
                continue
            fn = ACTIONS.get(st.get("do"))
            if fn is None:
                log.warning("unknown action %r", st.get("do"))
                continue
            try:
                # fades always use the real client: a momentary release fades them back itself
                c = self.ctx if ctx is None or st["do"] == "fade" else ctx
                if st["do"] in ROTARY:
                    await fn(c, st, int(st.get("ticks", 1)))
                else:
                    await fn(c, dict(st, _t0=t0, _src=src))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("action %s failed", st.get("do"))

    # --- encoders ---------------------------------------------------------

    def push(self, knob, pressed):
        k = self.knobs[knob]
        if pressed:
            k["held"], k["turned"] = True, False
            return
        k["held"] = False
        if k["turned"]:
            return
        l, m = self.encoder_map(knob)
        if m and "push" in m:
            key = (l, "push:" + knob)
            self.run(self.steps_for(m["push"], key, advance=True), key)

    async def turn(self, knob, direction):
        k = self.knobs[knob]
        now = time.monotonic()
        l, m = self.encoder_map(knob)
        mult = 1
        if k["dir"] == direction:
            for limit, mm in ACCEL.get(m.get("accel", "fine") if m else "fine", ACCEL["fine"]):
                if now - k["t"] <= limit:
                    mult = mm
                    break
        k["t"], k["dir"] = now, direction
        if k["held"]:
            k["turned"] = True
        if not m:
            return
        steps = m.get("push_turn") if k["held"] and m.get("push_turn") else m.get("turn", [])
        for st in steps:
            fn = ACTIONS.get(st.get("do"))
            if st.get("do") in ROTARY:
                try:
                    await fn(self.ctx, st, direction * mult)
                except Exception:
                    log.exception("rotary %s failed", st.get("do"))
