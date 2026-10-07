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

log = logging.getLogger("wingmacro")


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
        self.wing.on_connect.append(self._on_wing_connect)
        self.wing.listeners.append(self._on_wing_change)

    async def _on_wing_connect(self):
        await a_refresh(self.ctx, {})
        if self.leds:
            await self.wing.watch(self.leds.paths())

    def _on_wing_change(self, path, value):
        if path.startswith("/fx/") and path.endswith("/mdl"):
            slot = int(path.split("/")[2])
            self.ctx.fx_models[slot] = value
            self.ctx.invalidate_fx(slot)

    async def apply_config(self, cfg):
        """Validate, save and switch to a new config (from the web UI)."""
        C.validate(cfg)
        C.save(self.cfg_path, cfg)
        self.cfg = cfg
        if self.leds and self.wing.connected:
            await self.wing.watch(self.leds.paths())

    async def _pad_events(self):
        while True:
            ev = await self.pad.events.get()
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
