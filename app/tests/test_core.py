import asyncio
import struct

from wingmacro import wing as W
from wingmacro.actions import FLOOR, NEG_INF, perceptual, step_level
from wingmacro.engine import Engine


def test_escape_roundtrip():
    payload = bytes([0xD7, 0x02, 0xDF, 0xAF, 0x0E, 0xDF])
    u = W.Unescaper()
    assert u.feed(bytes([0xDF, 0xD1]) + W.escape(payload)) == payload


def test_parse_response_and_event():
    p = W.TokenParser()
    data = bytes.fromhex("d738ae75c2d5c3100000de") + bytes.fromhex("d7c6ad548d84") + b"Piano"
    out = p.feed(data[:7]) + p.feed(data[7:])
    assert out == [("val", 0x38AE75C2, -144.0), ("end",), ("val", 0xC6AD548D, "Piano")]


def test_encode_values():
    assert W.encode_value(1) == b"\x01"
    assert W.encode_value(200) == b"\xd3\x00\xc8"
    assert W.encode_value(-80.0) == b"\xd5" + struct.pack(">f", -80.0)
    assert W.encode_value("ab") == b"\x81ab"
    assert W.nav("/ch/1/fdr") == b"\xda\xc1ch\xc01\xc2fdr"


def test_fader_floor():
    assert step_level(NEG_INF, 0.1) == FLOOR
    assert step_level(NEG_INF, -0.1) == NEG_INF
    assert step_level(FLOOR, -0.1) == NEG_INF
    assert step_level(0.10000038, 0.1) == 0.2
    assert step_level(9.95, 0.1) == 10.0


def test_perceptual_curve_spends_time_above_minus_20():
    assert perceptual(0, -90, 0.5) > -20 + 10  # halfway is still loud (about -3 dB)
    assert perceptual(0, -90, 0.75) > -20
    assert abs(perceptual(0, -90, 1.0) + 90) < 1e-6
    assert perceptual(FLOOR, 0, 0.01) > -70  # fade-up is audible almost at once


def make_engine(buttons, **pad):
    cfg = {"pad": {"cancel_ms": 100, **pad}, "macros": {}, "layers": {"0": {"buttons": buttons}}}
    eng = Engine(lambda: cfg, ctx=None)
    fired = []
    eng.run = lambda steps, key, *a, **k: fired.append(steps[0]["v"])
    return eng, fired


def test_one_shot_fires_after_its_cancel_window_toggle_at_once():
    async def go():
        eng, fired = make_engine({"1": {"mode": "single", "do": [{"v": "a"}]},
                                  "2": {"mode": "toggle", "do": [{"v": "on"}], "off": [{"v": "off"}]},
                                  "3": {"mode": "single", "cancel_ms": 0, "do": [{"v": "now"}]}})
        eng.press(1, 0); assert fired == []
        eng.release(1, 0); assert fired == []            # armed: cancel window (100 ms here)
        await asyncio.sleep(0.15); assert fired == ["a"]
        eng.press(1, 0); eng.release(1, 0); eng.press(1, 0); eng.release(1, 0)   # tap again: cancelled
        await asyncio.sleep(0.15); assert fired == ["a"]
        eng.press(2, 1); eng.release(2, 1); assert fired == ["a", "on"]          # toggles: no cancel window
        eng.press(3, 2); eng.release(3, 2); assert fired == ["a", "on", "now"]   # cancel_ms 0: at once
    asyncio.run(go())


def test_hold_arm_fire_and_cancel():
    async def go():
        eng, fired = make_engine({"1": {"mode": "single", "hold": True, "hold_ms": 50, "do": [{"v": "h"}]}})
        eng.press(1, 0); await asyncio.sleep(0.01); eng.release(1, 0)   # too short
        await asyncio.sleep(0.15); assert fired == []
        eng.press(1, 0); await asyncio.sleep(0.06); eng.release(1, 0)   # armed
        await asyncio.sleep(0.15); assert fired == ["h"]
        eng.press(1, 0); await asyncio.sleep(0.06); eng.release(1, 0)   # armed, then tap
        await asyncio.sleep(0.03); eng.press(1, 0); eng.release(1, 0)
        await asyncio.sleep(0.15); assert fired == ["h"]
    asyncio.run(go())


def test_toggle_and_layer_fallback():
    cfg = {"pad": {}, "macros": {}, "layers": {"0": {"buttons": {"1": {
        "mode": "toggle", "do": [{"v": "On"}], "off": [{"v": "Off"}]}}}, "2": {"buttons": {}}}}
    eng = Engine(lambda: cfg, ctx=None)
    fired = []
    eng.run = lambda steps, key, *a, **k: fired.append(steps[0]["v"])
    eng.layer = 2  # falls back to layer 0
    for _ in range(3):
        eng.press(1, 0); eng.release(1, 0)
    assert fired == ["On", "Off", "On"]
    assert eng.toggles[(0, 1)] is True


def test_tap_moving_average():
    from types import SimpleNamespace
    from wingmacro.actions import a_tap, Context
    from wingmacro.wing import NodeDef, T_LINF
    written = []

    class FakeWing:
        async def defs(self, path):
            return [NodeDef("time", "TIME", 1, T_LINF, "ms", False, 1.0, 3000.0)]
        async def set(self, path, v):
            written.append((path, v))
    ctx = Context(FakeWing(), lambda: {})

    async def go():
        for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.6]:  # 500 ms x4, then one 600 ms interval
            await a_tap(ctx, {"slots": [3], "_t0": 100 + t})
        await a_tap(ctx, {"slots": [3], "_t0": 110.0})  # gap >= 2 s: starts over, no write
    asyncio.run(go())
    assert written[:4] == [("/fx/3/time", 500.0)] * 4
    assert written[4] == ("/fx/3/time", 526.3)  # window of 4: (500*3+600)/4 = 525 ms = 114.3 BPM -> 114 BPM
    assert len(written) == 5


def test_momentary_runs_on_then_off():
    from wingmacro.actions import Context

    class FakeWing:
        def __init__(self): self.v = {"/ch/40/mute": 1, "/mgrp/2/mute": 0}
        def cached(self, p, d=None): return self.v.get(p, d)
        async def value(self, p): return self.v.get(p)
        async def set(self, p, val): self.v[p] = val
    w = FakeWing()
    cfg = {"pad": {}, "macros": {}, "layers": {"0": {"buttons": {"1": {"mode": "momentary", "do": [
        {"do": "mute", "target": "ch/40", "op": "off"}, {"do": "mgrp", "n": 2, "op": "on"}],
        "off": [{"do": "mgrp", "n": 2, "op": "off"}, {"do": "mute", "target": "ch/40", "op": "on"}]}}}}}
    eng = Engine(lambda: cfg, Context(w, lambda: cfg))

    async def go():
        eng.press(1, 0); await asyncio.sleep(0.02)
        assert w.v == {"/ch/40/mute": 0, "/mgrp/2/mute": 1}   # active on key down
        eng.release(1, 0); await asyncio.sleep(0.02)
        assert w.v == {"/ch/40/mute": 1, "/mgrp/2/mute": 0}   # Off list on key up
    asyncio.run(go())


def test_led_actions_digico_style():
    from wingmacro.actions import Context

    class FakeWing:
        async def value(self, p): return 0
        async def set(self, p, v): pass
    cfg = {"pad": {}, "macros": {"lit": {"steps": [{"do": "led", "colour": "green"}]}}, "layers": {"0": {"buttons": {
        "1": {"mode": "toggle", "do": [{"do": "macro", "name": "lit"}, {"do": "led", "colour": "red"}],
              "off": [{"do": "led", "colour": "base"}]},
        "2": {"mode": "momentary", "do": [{"do": "led", "colour": "amber", "effect": "flash"},
                                          {"do": "led", "colour": "blue", "layer": 1, "key": 1}],
              "off": [{"do": "led", "colour": "base"}, {"do": "led", "colour": "red", "layer": 1, "key": 1}]}}}}}
    ctx = Context(FakeWing(), lambda: cfg)
    eng = Engine(lambda: cfg, ctx)

    async def go():
        eng.press(1, 0); eng.release(1, 0); await asyncio.sleep(0.01)   # On: macro (green) then red
        assert ctx.led_state[(0, 0)] == ("red", "solid")
        eng.press(1, 0); eng.release(1, 0); await asyncio.sleep(0.01)   # Off: back to key colour
        assert (0, 0) not in ctx.led_state
        eng.press(1, 0); eng.release(1, 0); await asyncio.sleep(0.01)
        eng.press(2, 1); await asyncio.sleep(0.01)                     # momentary: own key + key 1
        assert ctx.led_state[(0, 1)] == ("amber", "flash") and ctx.led_state[(0, 0)] == ("blue", "solid")
        eng.release(2, 1); await asyncio.sleep(0.01)
        assert (0, 1) not in ctx.led_state and ctx.led_state[(0, 0)] == ("red", "solid")
    asyncio.run(go())


def test_migration():
    from wingmacro.config import migrate, _auto_off
    on = [{"do": "mgrp", "n": 1, "op": "on"}, {"do": "fade", "target": "ch/1", "db": "-inf", "time": 5},
          {"do": "wait", "ms": 100}, {"do": "led", "colour": "red"}]
    assert _auto_off(on) == [{"do": "led", "colour": "base"}, {"do": "fade", "target": "ch/1", "db": "back", "time": 5},
                                 {"do": "mgrp", "n": 1, "op": "off"}]
    cfg = {"layers": {"0": {"buttons": {
        "1": {"do": [{"do": "mute", "target": "ch/1", "op": "toggle"}]},
        "2": {"do": {"toggle": ["a", [{"do": "refresh"}]]}, "led": {"bind": "connected"}},
        "3": {"do": "a"}}, "encoders": {}}},
        "macros": {"a": {"retrigger": "ignore", "steps": [{"do": "softmute", "target": "aux/1", "op": "down", "time": 4}]}}}
    assert migrate(cfg) and cfg["version"] == 5
    assert cfg["macros"]["a"]["steps"] == [{"do": "fade", "target": "aux/1", "time": 4, "db": "-inf"},
                                           {"do": "mute", "target": "aux/1", "op": "on"}]
    b = cfg["layers"]["0"]["buttons"]
    # v4: the old automatic Off is written out; custom Off lists are kept. v5: mode instead of trigger/toggle
    assert b["1"] == {"do": [{"do": "mute", "target": "ch/1", "op": "on"}], "mode": "toggle",
                      "off": [{"do": "mute", "target": "ch/1", "op": "off"}]}
    assert b["2"] == {"do": [{"do": "macro", "name": "a"}], "off": [{"do": "refresh"}], "mode": "toggle"}
    assert b["3"]["do"] == [{"do": "macro", "name": "a"}] and "retrigger" not in cfg["macros"]["a"]


def test_vial_macro_roundtrip():
    from wingmacro import vialmacro as V
    macros = [[{"text": "hi"}, {"tap": [0x3A, 0x0104]}, {"delay": 600}, {"down": [0xE0]}, {"tap": [0x7E00]}, {"up": [0xE0]}], [], [{"text": "x"}]]
    buf = V.encode(macros)
    assert 0 not in buf[:buf.index(0)]  # no stray terminators inside macro 0
    assert V.decode(buf + b"\0" * 20, 4) == macros + [[]]


def test_bloom_swells_out_of_the_fired_key_and_back():
    from wingmacro.leds import Leds
    from wingmacro.actions import Context

    class FakePad:
        keymap = []
        connected = False
    cfg = {"pad": {"background": "off"}, "macros": {}, "layers": {"0": {"buttons": {}}}}
    ctx = Context(None, lambda: cfg)
    leds = Leds(lambda: cfg, FakePad(), None, ctx)
    leds.engine = Engine(lambda: cfg, ctx, leds)
    leds.transient(5, "confirm", None, {"fire_anim": "burst", "hold_colour": "red"})   # old name still works
    t0 = leds.blooms[5][0]
    mid = leds.frame(t0 + 0.4)                      # widest: the key, its neighbours, not the far side
    assert mid[5][2] == 200 and all(mid[i][2] > 90 for i in (1, 4, 6, 9)) and mid[15][2] == 0
    assert leds.frame(t0 + 0.05)[4][2] < mid[4][2]   # still growing
    end = leds.frame(t0 + 2 * leds.BLOOM_HALF + 0.05)
    assert not leds.blooms and all(c[2] == 0 for c in end)


def test_param_labels():
    from wingmacro.params import param_label, node_label
    assert param_label("/ch/3/eq/1g", "GAIN 1") == "Band 1 gain"
    assert param_label("/ch/3/eq/on", "EQ") == "EQ on"
    assert param_label("/ch/3/send/MX2/on") == "Send on"
    assert param_label("/fx/2/lc", "LO CUT") == "Lo cut"  # FX: console name, not the strip meaning
    assert param_label("/ch/1/newthing", "NEW THING L") == "New thing L"
    assert node_label("/main") == "Mains" and node_label("/ch/1/main") == "Main sends"


def test_param_actions_follow_console_defs():
    from wingmacro.actions import Context, a_param, a_param_set
    from wingmacro.wing import NodeDef, T_LINF, T_ENUM, T_INT

    class FakeWing:
        def __init__(self): self.v = {"/ch/1/dyn/thr": -10.0, "/ch/1/dyn/det": "PEAK", "/ch/1/dyn/on": 0}
        async def defs(self, node):
            assert node == "/ch/1/dyn"
            return [NodeDef("thr", "THR", 1, T_LINF, "dB", False, -60.0, 0.0),
                    NodeDef("det", "DETECTOR", 2, T_ENUM, "", False, items=["PEAK", "RMS"]),
                    NodeDef("on", "DYNAMICS", 3, T_INT, "", False, 0, 1)]
        async def value(self, p): return self.v.get(p)
        async def set(self, p, val): self.v[p] = val
    w = FakeWing(); ctx = Context(w, lambda: {})

    async def go():
        await a_param(ctx, {"path": "ch/1/dyn/thr"}, 3)            # linf, range >= 10: 0.1 steps
        await a_param(ctx, {"path": "/ch/1/dyn/thr", "step": 50}, 1)  # clamped to max
        await a_param_set(ctx, {"path": "/ch/1/dyn/det", "op": "inc"})
        await a_param_set(ctx, {"path": "/ch/1/dyn/det", "op": "inc"})   # stops at the end (no wrap)
        await a_param_set(ctx, {"path": "/ch/1/dyn/on", "value": "1"})
    asyncio.run(go())
    assert w.v == {"/ch/1/dyn/thr": 0.0, "/ch/1/dyn/det": "RMS", "/ch/1/dyn/on": 1}
    ctx.invalidate("/ch/1")
    assert ctx.node_defs_cache == {}


def test_v5_key_modes_and_fx_actions():
    from wingmacro.config import migrate
    cfg = {"version": 4, "macros": {"m": {"steps": [{"do": "fx_set", "slot": 2, "param": "time", "value": 300}]}},
           "layers": {"0": {"buttons": {
               "1": {"trigger": "hold", "toggle": True, "do": [{"do": "fx_cycle", "slot": 3, "param": "fact", "dir": "prev"}], "off": []},
               "2": {"trigger": "momentary", "do": [{"do": "mute", "target": "ch/9", "op": "off"}]},
               "3": {"trigger": "press", "do": [{"do": "refresh"}], "off": [{"do": "wait"}]}},
               "encoders": {"left": {"turn": [{"do": "fx", "slot": 1, "param": "dcy", "step": 0.1},
                                              {"do": "param_cycle", "path": "/ch/1/eq/mdl"}]}}}}}
    assert migrate(cfg) and cfg["version"] == 5
    b = cfg["layers"]["0"]["buttons"]
    assert b["1"] == {"mode": "toggle", "hold": True, "off": [],
                      "do": [{"do": "param_set", "path": "/fx/3/fact", "op": "dec", "wrap": True}]}
    assert b["2"] == {"mode": "momentary", "do": [{"do": "mute", "target": "ch/9", "op": "off"}],
                      "off": [{"do": "mute", "target": "ch/9", "op": "on"}]}
    assert b["3"] == {"mode": "single", "do": [{"do": "refresh"}]}
    assert cfg["layers"]["0"]["encoders"]["left"]["turn"] == [
        {"do": "param", "path": "/fx/1/dcy", "step": 0.1}, {"do": "param", "path": "/ch/1/eq/mdl"}]
    assert cfg["macros"]["m"]["steps"] == [{"do": "param_set", "path": "/fx/2/time", "value": 300}]


def test_fire_anim_colour_and_bloom():
    from wingmacro.leds import Leds
    L = Leds.__new__(Leds)
    L.engine = None
    L.cfg = lambda: {"pad": {"background": [22, 255, 47]}}
    assert L.anim_colour({}) == (22, 255, 200)                       # pad background, full brightness
    assert L.anim_colour({"background": [128, 255, 60]}) == (128, 255, 200)  # the key's own colour
    assert L.anim_colour({"background": "off"}) == (0, 0, 200)        # an unlit key animates white
    assert L.anim_colour({"hold_colour": "red"})[2] == 200
    near = [L.bloom_level(1, e) for e in (0.1, 0.4, 0.79)]
    L.blooms = {}
    assert near[0] < near[1] and near[2] < 0.05                       # swells out, then back in
    assert max(L.bloom_level(3, e / 100) for e in range(80)) < 0.01   # never reaches the far side


def test_momentary_bloom_holds_while_down_and_toggle_shows_state():
    from wingmacro.leds import Leds
    from wingmacro.actions import Context

    class FakePad:
        keymap = []
        connected = False
    cfg = {"pad": {"background": [22, 255, 47]}, "macros": {}, "layers": {"0": {"buttons": {
        "6": {"mode": "momentary", "do": [], "off": []}, "1": {"mode": "toggle", "do": [], "off": []}}}}}
    ctx = Context(None, lambda: cfg)
    leds = Leds(lambda: cfg, FakePad(), None, ctx)
    leds.engine = Engine(lambda: cfg, ctx, leds)
    m = cfg["layers"]["0"]["buttons"]["6"]
    leds.transient(5, "held", None, m)              # momentary default animation: bloom
    t0 = leds.blooms[5][0]
    a, b = leds.frame(t0 + 0.5), leds.frame(t0 + 3.0)
    assert a[5][2] == 200 and a[4][2] > 90 and b[4][2] == a[4][2]   # held at its widest
    leds.transient(5, "release", None, m)
    tr = leds.blooms[5][2]
    assert leds.frame(tr + 0.2)[4][2] < b[4][2] and leds.frame(tr + 0.45)[4][2] == 47 and not leds.blooms
    leds.engine.toggles[(0, 1)] = True               # toggle on: full brightness; off: own colour
    assert leds.frame(tr + 1)[0] == (22, 255, 200)
    leds.engine.toggles[(0, 1)] = False
    assert leds.frame(tr + 1)[0] == (22, 255, 47)


def test_tap_key_fires_on_key_down_without_cancel_window():
    eng, fired = make_engine({"1": {"mode": "single", "do": [{"do": "tap", "slots": [3], "v": "t"}]}})
    eng.expand = lambda steps, depth=0: steps
    for _ in range(3):
        eng.press(1, 0); assert fired[-1] == "t"
        eng.release(1, 0)
    assert fired == ["t", "t", "t"] and not eng.buttons


def test_beat_flash_off_flashes_8_beats_after_the_tap():
    from wingmacro.leds import Leds
    from wingmacro.actions import Context
    ctx = Context(None, lambda: {})
    L = Leds(lambda: {"pad": {"background": [22, 255, 47]}}, None, None, ctx)
    ctx.taps[(3,)] = {"t": [100.0], "ms": 500.0}
    base = (22, 255, 47)
    lit = lambda step, beat: L._tap(100.0 + beat * 0.5 + 0.01, base, step, {})[2] == 200
    on, off = {"do": "tap", "slots": [3]}, {"do": "tap", "slots": [3], "flash": False}
    assert lit(on, 20)                                              # flash on: every beat
    assert all(lit(off, b) for b in range(1, 9)) and not lit(off, 9)  # off: 8 beats after the tap, then rest
