"""Wires pad, WING client, engine, LEDs and web UI together."""
import asyncio
import logging
import signal

from . import config as C
from .actions import Context, a_refresh
from .engine import Engine
from .leds import Leds
from .pad import Pad
from .web import start_web
from .wing import Wing
from . import vialmacro

log = logging.getLogger("wingmacro")

STRIPS = [("ch", 40), ("aux", 8), ("bus", 16), ("main", 4), ("mtx", 8), ("dca", 16), ("mgrp", 8)]


class App:
    def __init__(self, cfg_path, wing_ip=None, use_pad=True):
        self.cfg_path = cfg_path
        self.cfg = C.load(cfg_path)
        ip = wing_ip or self.cfg.get("console", {}).get("ip") or None
        self.wing = Wing(ip)
        self.pad = Pad() if use_pad else None
        self.ctx = Context(self.wing, lambda: self.cfg)
        self.leds = Leds(lambda: self.cfg, self.pad, self.wing, self.ctx) if self.pad else None
        self.engine = Engine(lambda: self.cfg, self.ctx, self.leds)
        if self.leds:
            self.leds.engine = self.engine
        self.vial = None  # cached Vial extras read from the pad
        self.unlock = {"unlocked": False, "in_progress": False, "counter": 0}
        self.wing.on_connect.append(self._on_wing_connect)
        self.wing.listeners.append(self._on_wing_change)

    async def _on_wing_connect(self):
        await a_refresh(self.ctx, {})
        names = [f"/{k}/{n}/{f}" for k, cnt in STRIPS for n in range(1, cnt + 1) for f in ("name", "col")
                 if not (k == "mgrp" and f == "col")]
        await self.wing.watch(names)

    def _on_wing_change(self, path, value):
        if path.startswith("/fx/") and path.endswith("/mdl"):
            slot = int(path.split("/")[2])
            self.ctx.fx_models[slot] = value
            self.ctx.invalidate_fx(slot)

    def strips(self):
        """Names/colours of every fader-type strip and mute group, from the WING value cache."""
        c = self.wing.cached
        return {k: [{"n": n, "name": c(f"/{k}/{n}/name") or "", "col": c(f"/{k}/{n}/col")}
                    for n in range(1, cnt + 1)] for k, cnt in STRIPS}

    def pad_keys(self):
        """Per layer, the WM id at each of the 16 key positions (None = not a WM key)."""
        p = self.pad
        if not p or not p.keymap:
            return {"known": False, "layers": [[i + 1 for i in range(16)] for _ in range(4)]}
        return {"known": True, "layers": [[p.key_wm(l, i) for i in range(16)] for l in range(len(p.keymap))]}

    def keymap(self):
        p = self.pad
        return {"connected": bool(p and p.connected and p.keymap), "cols": 5,
                "layers": p.keymap if p else [], "encoders": p.encmap if p else []}

    async def set_keycode(self, body):
        """Write one keycode to the pad: {layer,row,col,kc} or {layer,encoder,cw,kc}."""
        p = self.pad
        if not (p and p.connected):
            raise ValueError("pad not connected")
        kc = int(body["kc"]) & 0xFFFF
        if kc == 0x7C00:
            raise ValueError("QK_BOOT needs the pad unlocked: assign it in Vial")
        loop = asyncio.get_running_loop()
        if "encoder" in body:
            await loop.run_in_executor(None, p.set_encoder, int(body["layer"]), int(body["encoder"]), body["cw"], kc)
        else:
            await loop.run_in_executor(None, p.set_key, int(body["layer"]), int(body["row"]), int(body["col"]), kc)

    # --- Vial extras (unlock, keystroke macros, tap dance, combos) ------------------

    async def _pad_call(self, fn, *a):
        if not (self.pad and self.pad.connected):
            raise ValueError("pad not connected")
        return await asyncio.get_running_loop().run_in_executor(None, fn, *a)

    async def vial_state(self, reload=False):
        p = self.pad
        if not (p and p.connected):
            self.vial = None
            return {"connected": False}
        if self.vial is None or reload:
            def read():
                counts = p.entry_counts()
                mcount, msize = p.macro_info()
                buf = p.get_macro_buffer()
                return {
                    "tap_dance": [p.get_tap_dance(i) for i in range(counts["tap_dance"])],
                    "combos": [p.get_combo(i) for i in range(counts["combos"])],
                    "macros": vialmacro.decode(buf, mcount), "macro_size": msize,
                }
            self.vial = await self._pad_call(read)
            st = await self._pad_call(p.unlock_status)
            self.unlock.update(unlocked=st["unlocked"], keys=st["keys"])
        used = len(vialmacro.encode(self.vial["macros"]))
        return dict(self.vial, connected=True, macro_used=used, unlock=self.unlock)

    async def vial_unlock(self):
        """Start Vial's unlock: the user holds the unlock keys; we poll until done (or 30 s)."""
        p = self.pad
        await self._pad_call(p.unlock_start)
        self.unlock.update(in_progress=True, counter=50)

        async def poll():
            t0 = asyncio.get_running_loop().time()
            try:
                while asyncio.get_running_loop().time() - t0 < 30:
                    st = await self._pad_call(p.unlock_poll)
                    self.unlock.update(st)
                    if st["unlocked"] or not st["in_progress"]:
                        break
                    await asyncio.sleep(0.12)
            except (ValueError, OSError) as e:
                log.warning("unlock: %s", e)
            self.unlock["in_progress"] = False
        asyncio.create_task(poll())

    async def vial_lock(self):
        await self._pad_call(self.pad.lock)
        self.unlock.update(unlocked=False, in_progress=False)

    async def vial_set(self, kind, body):
        p = self.pad
        if self.vial is None:
            await self.vial_state()
        if kind == "tap_dance":
            idx, td = int(body["idx"]), {k: int(body[k]) & 0xFFFF for k in ("tap", "hold", "double_tap", "tap_hold", "term")}
            await self._pad_call(p.set_tap_dance, idx, td)
            self.vial["tap_dance"][idx] = td
        elif kind == "combo":
            idx = int(body["idx"])
            combo = {"inputs": [int(x) & 0xFFFF for x in body["inputs"]][:4], "output": int(body["output"]) & 0xFFFF}
            await self._pad_call(p.set_combo, idx, combo)
            self.vial["combos"][idx] = dict(combo, inputs=(combo["inputs"] + [0, 0, 0, 0])[:4])
        elif kind == "macros":
            if not self.unlock.get("unlocked"):
                raise ValueError("unlock the pad first (Vial only allows macro changes when unlocked)")
            macros = body["macros"]
            await self._pad_call(p.set_macro_buffer, vialmacro.encode(macros))
            self.vial["macros"] = macros

    async def set_console(self, ip):
        cfg = dict(self.cfg, console=dict(self.cfg.get("console", {}), ip=ip or ""))
        C.save(self.cfg_path, cfg)
        self.cfg = cfg
        self.wing.set_host(ip or None)

    async def apply_config(self, cfg):
        """Validate, save and switch to a new config (from the web UI)."""
        C.validate(cfg)
        C.save(self.cfg_path, cfg)
        self.cfg = cfg

    async def _pad_events(self):
        while True:
            ev = await self.pad.events.get()
            if ev["type"] in ("connected", "disconnected"):
                self.vial = None
                self.unlock.update(unlocked=False, in_progress=False)
            try:
                await self.engine.handle(ev)
            except Exception:
                log.exception("event %s", ev)

    async def run(self, web_host, web_port):
        tasks = [asyncio.create_task(self.wing.run())]
        if self.pad:
            tasks += [asyncio.create_task(self.pad.run()),
                      asyncio.create_task(self._pad_events()),
                      asyncio.create_task(self.leds.run())]
        runner = await start_web(self, web_host, web_port)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows
                pass
        try:
            await stop.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await runner.cleanup()
            if self.pad:
                self.pad.close()
