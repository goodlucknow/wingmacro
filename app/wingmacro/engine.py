"""Pad events -> mappings -> macros. See docs/config-model.md."""
import asyncio
import logging
import time

from .actions import ACTIONS, ROTARY

log = logging.getLogger(__name__)

PUSH_POS = {(0, 4): "left", (1, 4): "right"}
KNOBS = ["left", "right"]
ROW_CW, ROW_CCW = 253, 252
CHARGE = 0.2  # s: the LED "charge" on key down for keys without hold to fire
# (max seconds between ticks, step multiplier); slower than all thresholds = 1 step per tick
ACCEL = {
    "off": [],
    "fine": [(0.03, 4), (0.06, 2)],
    "normal": [(0.02, 10), (0.04, 5), (0.08, 2)],
}


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
        if m.get("mode") != "toggle":
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
                    self._momentary_end(st)  # pad gone mid-press: still run the key-up list
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
        if m.get("mode") == "momentary":
            self._momentary_start(st)
        elif m.get("hold"):
            st["phase"] = "holding"
            st["hold"] = m.get("hold_ms", pad.get("hold_ms", 800)) / 1000
            self._led(st, "progress", st["hold"])
        else:
            self._led(st, "progress", CHARGE)  # same charge-and-release feel as a hold key, just quick
        self.buttons[wm] = st

    def release(self, wm, idx):
        st = self.buttons.get(wm)
        if not st:
            return
        if st["phase"] == "pressed":
            if st["map"].get("mode", "single") == "single" and self._cancel_s(st) > 0:
                self._arm(st)  # one-shots get a cancel window too
            else:
                del self.buttons[wm]
                self.fire(st)
        elif st["phase"] == "held":
            del self.buttons[wm]
            self._momentary_end(st)
        elif st["phase"] == "cancelling":
            del self.buttons[wm]
        elif st["phase"] == "holding":
            if time.monotonic() - st["t0"] >= st["hold"]:
                self._arm(st)
            else:
                del self.buttons[wm]
                self._led(st, "clear")

    def _cancel_s(self, st):
        return st["map"].get("cancel_ms", self.cfg().get("pad", {}).get("cancel_ms", 400)) / 1000

    def _arm(self, st):
        """Released: wait out the cancel window (a press of the same key cancels), then fire."""
        cancel = self._cancel_s(st)
        st["phase"] = "armed"
        st["timer"] = asyncio.get_running_loop().call_later(cancel, self._armed_fire, st["wm"])
        self._led(st, "armed", cancel)

    def _armed_fire(self, wm):
        st = self.buttons.pop(wm, None)
        if st:
            self.fire(st)

    def fire(self, st):
        self._led(st, "confirm")
        key = (st["layer"], st["wm"])
        self.run(self.steps_for(st["map"], key, advance=True), key, t0=st["t0"], src=self._src(st))

    @staticmethod
    def _src(st):
        """LED address of the key that fired: (mapping layer, key index)."""
        return (st["layer"], st["idx"]) if st.get("idx") is not None else None

    def _momentary_start(self, st):
        """Key down: run the On list. Key up runs the Off list under the same key, so it takes
        over from an On list that is still running (e.g. a fade)."""
        st["phase"] = "held"
        self._led(st, "held")
        self.run(st["map"].get("do") or [], (st["layer"], st["wm"]), t0=st["t0"], src=self._src(st))

    def _momentary_end(self, st):
        self._led(st, "release")
        self.run(st["map"].get("off") or [], (st["layer"], st["wm"]), src=self._src(st))

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
        if m.get("mode") == "momentary":
            self._momentary_start(st)
            asyncio.get_running_loop().call_later(1.0, self._momentary_end, st)
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
                c = self.ctx if ctx is None else ctx
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
