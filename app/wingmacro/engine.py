"""Pad events -> mappings -> macros. See docs/config-model.md."""
import asyncio
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


class Engine:
    def __init__(self, cfg_ref, ctx, leds=None):
        self.cfg = cfg_ref
        self.ctx = ctx
        self.leds = leds
        self.layer = 0
        self.buttons = {}  # wm -> state
        self.knobs = {k: {"held": False, "turned": False, "t": 0.0, "dir": 0} for k in KNOBS}
        self.toggles = {}  # (layer, wm/knob) -> 0/1
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

    def resolve(self, do, toggle_key=None, advance=False):
        """-> (steps, macro_key, retrigger). Toggles alternate between their two entries."""
        if isinstance(do, dict) and "toggle" in do:
            i = self.toggles.get(toggle_key, 0)
            if advance:
                self.toggles[toggle_key] = 1 - i
            return self.resolve(do["toggle"][i])
        if isinstance(do, str):
            m = self.cfg().get("macros", {}).get(do, {})
            return m.get("steps", []), do, m.get("retrigger", "restart")
        return do or [], None, "restart"

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
        if m.get("trigger", "press") == "hold":
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
        key = (st["layer"], st["wm"])
        steps, mkey, retrig = self.resolve(st["map"].get("do", []), key, advance=True)
        self.run(steps, mkey or key, retrig)

    def _led(self, st, kind, dur=None):
        if self.leds and st.get("idx") is not None:
            self.leds.transient(st["idx"], kind, dur, st["map"])

    # --- macros -----------------------------------------------------------

    def run(self, steps, key, retrigger="restart"):
        old = self.running.get(key)
        if old and not old.done():
            if retrigger == "ignore":
                return
            if retrigger == "restart":
                old.cancel()
        task = asyncio.create_task(self._run(steps, key))
        if retrigger != "parallel":
            self.running[key] = task

    async def _run(self, steps, key):
        try:
            for st in steps:
                fn = ACTIONS.get(st.get("do"))
                if fn is None:
                    log.warning("unknown action %r", st.get("do"))
                    continue
                try:
                    if st["do"] in ROTARY:
                        await fn(self.ctx, st, int(st.get("ticks", 1)))
                    else:
                        await fn(self.ctx, st)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("action %s failed", st.get("do"))
        finally:
            if self.running.get(key) is asyncio.current_task():
                del self.running[key]

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
            steps, mkey, retrig = self.resolve(m["push"].get("do", []), (l, knob), advance=True)
            self.run(steps, mkey or (l, knob, "push"), retrig)

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
