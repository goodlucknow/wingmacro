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
    eng.run = lambda steps, key, *a: fired.append(steps[0]["v"])
    return eng, fired


def test_press_fires_on_release():
    eng, fired = make_engine({"1": {"trigger": "press", "do": [{"v": "a"}]}})
    eng.press(1, 0); assert fired == []
    eng.release(1, 0); assert fired == ["a"]


def test_hold_arm_fire_and_cancel():
    async def go():
        eng, fired = make_engine({"1": {"trigger": "hold", "hold_ms": 50, "do": [{"v": "h"}]}})
        eng.press(1, 0); await asyncio.sleep(0.01); eng.release(1, 0)   # too short
        await asyncio.sleep(0.15); assert fired == []
        eng.press(1, 0); await asyncio.sleep(0.06); eng.release(1, 0)   # armed
        await asyncio.sleep(0.15); assert fired == ["h"]
        eng.press(1, 0); await asyncio.sleep(0.06); eng.release(1, 0)   # armed, then tap
        await asyncio.sleep(0.03); eng.press(1, 0); eng.release(1, 0)
        await asyncio.sleep(0.15); assert fired == ["h"]
    asyncio.run(go())


def test_toggle_and_layer_fallback():
    cfg = {"pad": {}, "macros": {"a": {"steps": [{"v": "A"}]}, "b": {"steps": [{"v": "B"}]}},
           "layers": {"0": {"buttons": {"1": {"do": {"toggle": ["a", "b"]}}}}, "2": {"buttons": {}}}}
    eng = Engine(lambda: cfg, ctx=None)
    fired = []
    eng.run = lambda steps, key, *a: fired.append(steps[0]["v"])
    eng.layer = 2  # falls back to layer 0
    for _ in range(3):
        eng.press(1, 0); eng.release(1, 0)
    assert fired == ["A", "B", "A"]


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
    assert written[4] == ("/fx/3/time", 525.0)  # window of 4 intervals: (500*3+600)/4
    assert len(written) == 5


def test_momentary_restores_on_release():
    from wingmacro.actions import Context

    class FakeWing:
        def __init__(self): self.v = {"/ch/40/mute": 1, "/mgrp/2/mute": 0}
        def cached(self, p, d=None): return self.v.get(p, d)
        async def value(self, p): return self.v.get(p)
        async def set(self, p, val): self.v[p] = val
    w = FakeWing()
    cfg = {"pad": {}, "macros": {}, "layers": {"0": {"buttons": {"1": {"trigger": "momentary", "do": [
        {"do": "mute", "target": "ch/40", "op": "off"}, {"do": "mgrp", "n": 2, "op": "on"}]}}}}}
    eng = Engine(lambda: cfg, Context(w, lambda: cfg))

    async def go():
        eng.press(1, 0); await asyncio.sleep(0.02)
        assert w.v == {"/ch/40/mute": 0, "/mgrp/2/mute": 1}   # active on key down
        eng.release(1, 0); await asyncio.sleep(0.02)
        assert w.v == {"/ch/40/mute": 1, "/mgrp/2/mute": 0}   # put back on release
    asyncio.run(go())
