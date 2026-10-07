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
DELAYS = {"ST-DL", "TAP-DL", "TAPE-DL", "DEL/REV"}  # BBD-DL excluded (uses /dly)


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
        self.taps = []
        self.tap_ms = None
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


async def a_tap(ctx, p, ticks=None):
    now = time.monotonic()
    if ctx.taps and now - ctx.taps[-1] >= 2.0:
        ctx.taps = []
    ctx.taps = (ctx.taps + [now])[-8:]
    if len(ctx.taps) < 2:
        return
    period = (ctx.taps[-1] - ctx.taps[0]) / (len(ctx.taps) - 1)
    ctx.tap_ms = period * 1000
    for cb in ctx.on_beat:
        cb(period)
    slots = p.get("slots") or ctx.cfg().get("tap_tempo", {}).get("slots", {})
    if isinstance(slots, list):
        slots = {s: 1 for s in slots}
    for slot, mult in slots.items():
        slot = int(slot)
        model = ctx.fx_models.get(slot) or await ctx.wing.value(f"/fx/{slot}/mdl")
        if model not in DELAYS:
            log.info("tap: fx %d is %s, not a tap-tempo delay; skipped", slot, model)
            continue
        d = await ctx.fx_def(slot, "time")
        if d is None:
            continue
        ms = ctx.tap_ms * float(mult)
        if d.min is not None:
            ms = min(max(ms, d.min), d.max)
        await ctx.wing.set(f"/fx/{slot}/time", int(round(ms)) if d.type == W.T_INT else float(ms))


async def a_refresh(ctx, p, ticks=None):
    w = ctx.wing
    if not w.connected:
        return
    ctx.invalidate_fx()
    for slot in range(1, 17):
        ctx.fx_models[slot] = await w.get(f"/fx/{slot}/mdl")
    await w.refresh()
    log.info("refresh: fx %s", {k: v for k, v in ctx.fx_models.items() if v and v != "NONE"})


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


ACTIONS = {
    "mute": a_mute, "softmute": a_softmute, "mgrp": a_mgrp, "level_set": a_level_set,
    "level": a_level, "gain": a_gain, "fx": a_fx, "fx_cycle": a_fx_cycle, "fx_set": a_fx_set,
    "tap": a_tap, "refresh": a_refresh, "wait": a_wait, "set": a_set,
}
ROTARY = {"level", "gain", "fx", "fx_cycle"}
