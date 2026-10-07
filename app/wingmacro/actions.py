"""Macro actions. Each is `async fn(ctx, params, ticks=None)`; rotary actions get signed ticks."""
import asyncio
import logging
import math
import time

from . import wing as W

log = logging.getLogger(__name__)

NEG_INF = -144.0
FLOOR = -89.5  # lowest level above -inf (verified: -89.6 snaps to -inf)
FADE_END = -90.0
MAX_DB = 10.0
TAP_RESET = 2.0  # s gap that starts a new tap sequence
TAP_WINDOW = 4  # intervals in the moving average


# --- targets --------------------------------------------------------------

def is_send(target):
    return "/send/" in "/" + target.strip("/") + "/"


def level_path(target):
    t = "/" + target.strip("/")
    return t + ("/lvl" if is_send(t) else "/fdr")


def mute_path(target):
    """(path, inverted): sends have an 'on' switch instead of a mute."""
    t = "/" + target.strip("/")
    return (t + "/on", True) if is_send(t) else (t + "/mute", False)


def step_level(cur, delta):
    """Fader-floor rules: up from -inf jumps to FLOOR, below FLOOR snaps to -inf."""
    if cur is None:
        return None
    if cur < FLOOR - 0.01:
        return FLOOR if delta > 0 else NEG_INF
    new = round(cur + delta, 2)
    if new < FLOOR - 0.001:
        return NEG_INF
    return min(new, MAX_DB)


def perceptual(start_db, end_db, t):
    """Level at fraction t of a fade. Linear in loudness (2^(dB/10)), so most of the fade
    happens above about -20 dB, where it's audible."""
    a, b = 2 ** (start_db / 10), 2 ** (end_db / 10)
    return 10 * math.log2(a + (b - a) * min(max(t, 0.0), 1.0))


# --- context ----------------------------------------------------------------

class Context:
    def __init__(self, wing, cfg_ref):
        self.wing = wing
        self.cfg = cfg_ref  # callable returning current config
        self.fades = {}  # target -> (direction, task)
        self.softmute = {}  # target -> "down" | "up" | "fading_down" | "fading_up"
        self.fx_models = {}  # slot -> model name
        self.fx_defs = {}  # slot -> {param: NodeDef}
        self.taps = {}  # slots key -> {"t": [press times], "ms": period or None}
        self.led_state = {}  # (mapping layer, key index) -> (colour, effect), set by `led` actions
        self.led_record = None  # during a momentary press: {key: previous state} for restore
        self.on_beat = []  # fn(period_s)

    async def fx_def(self, slot, param):
        if slot not in self.fx_defs:
            defs = await self.wing.defs(f"/fx/{slot}")
            self.fx_defs[slot] = {d.name: d for d in defs}
        return self.fx_defs[slot].get(param)

    def invalidate_fx(self, slot=None):
        if slot is None:
            self.fx_defs.clear()
        else:
            self.fx_defs.pop(slot, None)


async def _toggle_bool(ctx, path, op, inverted=False):
    cur = await ctx.wing.value(path)
    if cur is None:
        log.warning("%s: no value", path)
        return
    state = bool(cur) != inverted  # "muted"
    want = {"on": True, "off": False}.get(op, not state)
    await ctx.wing.set(path, int(want != inverted))


# --- button actions -------------------------------------------------------

async def a_mute(ctx, p, ticks=None):
    path, inv = mute_path(p["target"])
    await _toggle_bool(ctx, path, p.get("op", "toggle"), inv)


async def a_mgrp(ctx, p, ticks=None):
    await _toggle_bool(ctx, f"/mgrp/{int(p['n'])}/mute", p.get("op", "toggle"))


async def a_level_set(ctx, p, ticks=None):
    db = p.get("db", 0)
    db = NEG_INF if db == "-inf" else float(db)
    if db < FLOOR - 0.001:
        db = NEG_INF
    await ctx.wing.set(level_path(p["target"]), db)


async def a_softmute(ctx, p, ticks=None):
    target = p["target"]
    op = p.get("op", "toggle")
    if op == "toggle":
        st = ctx.softmute.get(target)
        if st is None:
            mpath, inv = mute_path(target)
            muted = bool(await ctx.wing.value(mpath)) != inv
            lvl = await ctx.wing.value(level_path(target))
            st = "down" if muted or (lvl is not None and lvl < FLOOR - 0.01) else "up"
        op = "up" if st in ("down", "fading_down") else "down"
    old = ctx.fades.pop(target, None)
    if old:
        old[1].cancel()
    task = asyncio.create_task(_fade(ctx, target, op, float(p.get("time", 5))))
    ctx.fades[target] = (op, task)


async def _fade(ctx, target, op, secs):
    lpath = level_path(target)
    mpath, inv = mute_path(target)
    w = ctx.wing
    try:
        cur = await w.value(lpath)
        if cur is None:
            return
        if op == "down":
            ctx.softmute[target] = "fading_down"
            start, end = max(cur, FADE_END), FADE_END
            if cur < FLOOR - 0.01:
                secs = 0
        else:
            ctx.softmute[target] = "fading_up"
            start, end = (cur if cur >= FLOOR else FLOOR), 0.0
            await w.set(lpath, start)
            await w.set(mpath, int(inv))  # unmute
        t0 = time.monotonic()
        while True:
            t = (time.monotonic() - t0) / secs if secs > 0 else 1.0
            if t >= 1.0:  # never finish early: only after the full time has elapsed
                break
            db = perceptual(start, end, t)
            await w.set(lpath, NEG_INF if db < FLOOR else round(db, 2))
            await asyncio.sleep(0.02)
        if op == "down":
            await w.set(lpath, NEG_INF)
            await w.set(mpath, int(not inv))  # mute
            ctx.softmute[target] = "down"
        else:
            await w.set(lpath, end)
            ctx.softmute[target] = "up"
    finally:
        if ctx.fades.get(target, (None, None))[1] is asyncio.current_task():
            del ctx.fades[target]


def tap_key(p):
    return tuple(sorted(int(x) for x in p.get("slots", [])))


async def a_tap(ctx, p, ticks=None):
    """Moving average of the last TAP_WINDOW tap intervals, written as-is to /fx/N/time of each
    slot in `slots`. The delay's own `fact` (subdivision) stays on the console. Slots without a
    `time` param in ms (e.g. BBD-DL, which uses /dly) are skipped."""
    st = ctx.taps.setdefault(tap_key(p), {"t": [], "ms": None})
    now = p.get("_t0", time.monotonic())  # press time, so release timing doesn't add jitter
    if st["t"] and now - st["t"][-1] >= TAP_RESET:
        st["t"] = []
    st["t"] = (st["t"] + [now])[-(int(p.get("window", TAP_WINDOW)) + 1):]
    if len(st["t"]) < 2:
        return
    period = (st["t"][-1] - st["t"][0]) / (len(st["t"]) - 1)
    st["ms"] = period * 1000
    for slot in tap_key(p):
        d = await ctx.fx_def(slot, "time")
        if d is None or d.unit != "ms" or d.readonly:
            log.info("tap: fx %d (%s) has no time param in ms; skipped", slot, ctx.fx_models.get(slot))
            continue
        ms = min(max(st["ms"], d.min), d.max) if d.min is not None else st["ms"]
        await ctx.wing.set(f"/fx/{slot}/time", int(round(ms)) if d.type == W.T_INT else round(ms, 1))


async def a_refresh(ctx, p, ticks=None):
    w = ctx.wing
    if not w.connected:
        return
    ctx.invalidate_fx()
    for slot in range(1, 17):
        ctx.fx_models[slot] = await w.get(f"/fx/{slot}/mdl")
    await w.refresh()
    log.info("refresh: fx %s", {k: v for k, v in ctx.fx_models.items() if v and v != "NONE"})


async def a_led(ctx, p, ticks=None):
    """Set a key's colour (DiGiCo-style). Default target: the key that ran the macro.
    `layer`/`key` (1-based) address another key; colour "base" returns it to its own colour."""
    if p.get("key"):
        target = (int(p.get("layer", 1)) - 1, int(p["key"]) - 1)
    else:
        target = p.get("_src")
    if target is None:
        log.info("led: no target key (knob actions must name a key)")
        return
    target = tuple(target)
    if ctx.led_record is not None and target not in ctx.led_record:
        ctx.led_record[target] = ctx.led_state.get(target)
    if p.get("colour", "base") == "base":
        ctx.led_state.pop(target, None)
    else:
        ctx.led_state[target] = (p["colour"], p.get("effect", "solid"))


async def a_wait(ctx, p, ticks=None):
    await asyncio.sleep(float(p.get("ms", 0)) / 1000)


async def a_set(ctx, p, ticks=None):
    await ctx.wing.set(p["path"], p["value"])


async def a_fx_set(ctx, p, ticks=None):
    slot, param = int(p["slot"]), p["param"]
    d = await ctx.fx_def(slot, param)
    if d is None:
        log.info("fx %d has no param %s (model/mode)", slot, param)
        return
    v = p["value"]
    if d.type == W.T_INT:
        v = int(v)
    elif d.type in (W.T_LINF, W.T_LOGF, W.T_FADER):
        v = float(v)
    await ctx.wing.set(f"/fx/{slot}/{param}", v)


async def a_fx_cycle(ctx, p, ticks=None):
    n = ticks if ticks is not None else (-1 if p.get("dir") == "prev" else 1)
    await _fx_step(ctx, p, n)


# --- rotary actions -------------------------------------------------------

async def a_level(ctx, p, ticks):
    path = level_path(p["target"])
    cur = await ctx.wing.value(path)
    new = step_level(cur, ticks * float(p.get("step", 0.1)))
    if new is not None and new != cur:
        await ctx.wing.set(path, new)


async def a_gain(ctx, p, ticks):
    """Input gain of a channel's source (/io/in/<grp>/<n>/g)."""
    t = "/" + p["target"].strip("/")
    grp = await ctx.wing.value(t + "/in/conn/grp")
    n = await ctx.wing.value(t + "/in/conn/in")
    if not grp or grp == "OFF" or not n:
        return
    path = f"/io/in/{grp}/{n}/g"
    cur = await ctx.wing.value(path)
    if cur is not None:
        await ctx.wing.set(path, round(cur + ticks * float(p.get("step", 0.5)), 2))


def default_step(d):
    if d.type == W.T_INT:
        return 1
    if d.type == W.T_LINF:
        return 0.01 if (d.max - d.min) < 10 else 0.1
    if d.type == W.T_FADER:
        return 0.1
    return None


async def a_fx(ctx, p, ticks):
    await _fx_step(ctx, p, ticks)


async def _fx_step(ctx, p, ticks):
    slot, param = int(p["slot"]), p["param"]
    d = await ctx.fx_def(slot, param)
    if d is None or d.readonly:
        log.info("fx %d has no writable param %s (model/mode)", slot, param)
        return
    path = f"/fx/{slot}/{param}"
    cur = await ctx.wing.value(path)
    if cur is None:
        return
    if d.type in (W.T_ENUM, W.T_FENUM):
        items = d.items
        try:
            i = items.index(cur)
        except ValueError:
            i = min(range(len(items)), key=lambda k: abs(items[k] - cur)) if d.type == W.T_FENUM else 0
        new = items[(i + ticks) % len(items)]
    elif d.type == W.T_LOGF:
        pct = float(p.get("step", 0.01))  # value-proportional
        new = cur * (1 + pct) ** ticks
    elif d.type == W.T_FADER:
        new = step_level(cur, ticks * float(p.get("step", 0.1)))
    else:
        new = cur + ticks * float(p.get("step", default_step(d) or 1))
    if d.type in (W.T_INT, W.T_LINF, W.T_LOGF) and d.min is not None:
        new = min(max(new, d.min), d.max)
    if d.type == W.T_INT:
        new = int(round(new))
    elif isinstance(new, float):
        new = round(new, 4)
    if new != cur:
        await ctx.wing.set(path, new)


async def a_macro(ctx, p, ticks=None):
    """Placeholder: `macro` steps are expanded inline by the engine (Engine._steps)."""


INVERSE_OPS = {"mute": {"on": "off", "off": "on"}, "mgrp": {"on": "off", "off": "on"},
               "softmute": {"down": "up", "up": "down"}}


def inverse_steps(steps):
    """Automatic Off list for a toggle key: the On list reversed, with mutes/mute groups/soft mutes
    flipped and key colours set back to the key's own colour. Other actions have no inverse."""
    out = []
    for s in reversed(steps):
        d = s.get("do")
        if d in INVERSE_OPS and s.get("op") in INVERSE_OPS[d]:
            out.append(dict(s, op=INVERSE_OPS[d][s["op"]]))
        elif d == "led":
            out.append({k: v for k, v in s.items() if k in ("do", "layer", "key")} | {"colour": "base"})
    return out


ACTIONS = {
    "mute": a_mute, "softmute": a_softmute, "mgrp": a_mgrp, "level_set": a_level_set,
    "level": a_level, "gain": a_gain, "fx": a_fx, "fx_cycle": a_fx_cycle, "fx_set": a_fx_set,
    "tap": a_tap, "refresh": a_refresh, "wait": a_wait, "set": a_set, "led": a_led, "macro": a_macro,
}
ROTARY = {"level", "gain", "fx", "fx_cycle"}
