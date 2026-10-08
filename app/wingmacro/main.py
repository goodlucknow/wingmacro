"""Wires pad, WING client, engine, LEDs and web UI together."""
import asyncio
import logging
import signal
import threading

from . import config as C
from . import resolve as R
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
        self.ctx.on_beat.append(self._show_bpm)
        self.ctx.on_value.append(self._show_value)
        self._val_next, self._val_busy, self._val_lock = None, False, threading.Lock()
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
        if await self.stamp_params(self.cfg):
            C.save(self.cfg_path, self.cfg)

    async def stamp_params(self, cfg):
        """Remember what each param step on a modelled node (FX slot, insert) was picked as (`pref`),
        so it can be found again after a model change. Only for params the current model has.
        True if anything changed."""
        known = self.prefs()  # the UI's copy of the config may lack prefs stamped since it loaded
        changed = False
        for st in C.all_steps(cfg):
            path = st.get("path")
            if st.get("do") not in ("param", "param_set") or not path:
                continue
            path = "/" + path.strip("/")
            if (st.get("pref") or {}).get("path") == path:
                continue
            if path in known:
                st["pref"] = known[path]
                changed = True
                continue
            if not self.wing.connected:
                continue
            node = path.rpartition("/")[0]
            defs = await self.ctx.node_defs(node)
            d = defs.get(path.rpartition("/")[2])
            if "mdl" not in defs or d is None:
                continue
            st["pref"] = R.pref_of(path, await self.wing.value(node + "/mdl"), d)
            changed = True
        return changed

    def prefs(self):
        """{path: pref} of the current config's stamped param steps."""
        out = {}
        for st in C.all_steps(self.cfg or {}):
            pref = st.get("pref")
            if pref and pref.get("path") == "/" + (st.get("path") or "").strip("/"):
                out[pref["path"]] = pref
        return out

    def _on_wing_change(self, path, value):
        if path.startswith("/fx/") and path.endswith("/mdl"):
            slot = int(path.split("/")[2])
            self.ctx.fx_models[slot] = value
        if path.endswith("/mdl"):  # a model change replaces the node's parameters
            self.ctx.invalidate(path.rpartition("/")[0])

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

    async def set_pad_layer(self, layer):
        await self._pad_call(self.pad.set_layer, int(layer))

    def key_index(self, layer, wm):
        """LED index of the key holding WM `wm` on `layer` (from the pad keymap; default wm - 1)."""
        p = self.pad
        if p and p.keymap:
            for i in range(16):
                if p.key_wm(layer, i) == wm:
                    return i
            return None
        return wm - 1 if wm <= 16 else None

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

    def _show_bpm(self, period):
        """After a tap sets the tempo: show it on the pad's OLED for 2 s."""
        if self.pad and self.pad.connected and period > 0:
            asyncio.get_running_loop().run_in_executor(None, self.pad.show_bpm, 60 / period, 2.0)

    def _show_value(self, label, text):
        """A knob moved a value: show it on the pad's OLED. Fast turns send only the latest value."""
        if not (self.pad and self.pad.connected):
            return
        with self._val_lock:
            self._val_next = (label, text)
            if self._val_busy:
                return
            self._val_busy = True
        asyncio.get_running_loop().run_in_executor(None, self._send_values)

    def _send_values(self):
        while True:
            with self._val_lock:
                nxt, self._val_next = self._val_next, None
                if nxt is None:
                    self._val_busy = False
                    return
            try:
                self.pad.show_value(*nxt)
            except Exception as e:
                log.debug("show value: %s", e)

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

    # --- pad backup / restore (everything Vial stores in the pad's EEPROM) -------------

    async def pad_backup(self):
        st = await self.vial_state(reload=True)
        if not st.get("connected"):
            raise ValueError("pad not connected")
        p = self.pad
        return {"kind": "wingmacro-pad-backup", "version": 1, "keymap": p.keymap, "encoders": p.encmap,
                "tap_dance": st["tap_dance"], "combos": st["combos"], "macros": st["macros"]}

    async def pad_restore(self, b):
        """Write a backup to the pad. Macros are skipped (with a note) unless the pad is unlocked."""
        if b.get("kind") != "wingmacro-pad-backup":
            raise ValueError("not a wingmacro pad backup")
        p = self.pad

        def write():
            n = 0
            for l, keys in enumerate(b["keymap"][:len(p.keymap)]):
                for i, kc in enumerate(keys):
                    if kc != p.keymap[l][i] and kc != 0x7C00:
                        p.set_key(l, i // 5, i % 5, kc); n += 1
            for l, encs in enumerate(b["encoders"][:len(p.encmap)]):
                for e, pair in enumerate(encs):
                    for cw, kc in enumerate(pair):
                        if kc != p.encmap[l][e][cw]:
                            p.set_encoder(l, e, cw, kc); n += 1
            for i, td in enumerate(b.get("tap_dance", [])):
                if i < len(self.vial["tap_dance"]) and td != self.vial["tap_dance"][i]:
                    p.set_tap_dance(i, td); n += 1
            for i, c in enumerate(b.get("combos", [])):
                if i < len(self.vial["combos"]) and c != self.vial["combos"][i]:
                    p.set_combo(i, c); n += 1
            return n
        await self.vial_state(reload=True)
        changed = await self._pad_call(write)
        note = ""
        if b.get("macros") and b["macros"] != self.vial["macros"]:
            if self.unlock.get("unlocked"):
                await self._pad_call(p.set_macro_buffer, vialmacro.encode(b["macros"]))
                changed += 1
            else:
                note = "Key macros not restored: unlock the pad and restore again."
        self.vial = None
        return {"changed": changed, "note": note}

    async def set_console(self, ip):
        cfg = dict(self.cfg, console=dict(self.cfg.get("console", {}), ip=ip or ""))
        C.save(self.cfg_path, cfg)
        self.cfg = cfg
        self.wing.set_host(ip or None)

    async def apply_config(self, cfg):
        """Validate, save and switch to a new config (from the web UI or an import).
        Old-format configs (e.g. from a tab opened before an update) are converted first."""
        C.migrate(cfg)
        C.validate(cfg)
        await self.stamp_params(cfg)
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

    async def run(self, web_host, web_port, stop=None, ready=None):
        """Run until SIGINT/SIGTERM or `stop` is set. `ready()` is called once the web UI is up."""
        tasks = [asyncio.create_task(self.wing.run())]
        if self.pad:
            tasks += [asyncio.create_task(self.pad.run()),
                      asyncio.create_task(self._pad_events()),
                      asyncio.create_task(self.leds.run())]
        runner = await start_web(self, web_host, web_port)
        if ready:
            ready()
        stop = stop or asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, ValueError, RuntimeError):  # Windows, or not the main thread (tray)
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
