"""Local web UI: static single-page app + JSON API + a websocket for live state."""
import asyncio
import json
from pathlib import Path

from aiohttp import WSMsgType, web

from . import params as P
from .wing import discover

STATIC = Path(__file__).parent / "static"


def _status(app):
    w, p = app.wing, app.pad
    return {
        "wing": {"connected": w.connected, "host": w.host, "info": w.info},
        "pad": {"connected": bool(p and p.connected), "layer": app.engine.layer, "proto": p.proto if p else 0},
        "fx": {k: v for k, v in app.ctx.fx_models.items() if v and v != "NONE"},
        "tap_ms": {",".join(map(str, k)): v["ms"] for k, v in app.ctx.taps.items()},
        "toggles": {f"{l}/{k}": on for (l, k), on in app.engine.toggles.items()},
    }


async def start_web(app, host, port):
    async def index(_):
        return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    async def status(_):
        return web.json_response(_status(app))

    async def get_config(_):
        return web.json_response(app.cfg)

    async def put_config(req):
        try:
            cfg = json.loads(await req.text())
            await app.apply_config(cfg)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def strips(_):
        return web.json_response(app.strips())

    async def pad_keys(_):
        return web.json_response(app.pad_keys())

    async def fx_list(_):
        return web.json_response({str(k): v for k, v in app.ctx.fx_models.items()})

    async def params(req):
        """Children of a console node, labelled: {nodes: [{name, label}], params: [{...}]}.
        Fetched fresh (and refreshes the action cache), so model changes show at once."""
        node = "/" + req.query.get("path", "/").strip("/")
        defs = await app.wing.defs(node)
        if defs:
            app.ctx.node_defs_cache[node] = {d.name: d for d in defs}
        base = node.rstrip("/")
        nodes = sorted((d for d in defs if d.type == 0), key=lambda d: P.node_sort_key(d.name, not base))
        return web.json_response({
            "path": node, "label": P.node_label(node) if base else "Console",
            "nodes": [{"name": d.name, "label": P.node_label(f"{base}/{d.name}", d.longname)} for d in nodes],
            "params": [{"name": d.name, "label": P.param_label(f"{base}/{d.name}", d.longname),
                        "longname": d.longname, "type": d.type_name, "unit": d.unit, "min": d.min,
                        "max": d.max, "items": d.items, "readonly": d.readonly}
                       for d in defs if d.type != 0]})

    async def scan(_):
        found = await asyncio.get_running_loop().run_in_executor(None, discover)
        return web.json_response(found)

    async def set_console(req):
        body = await req.json()
        await app.set_console((body.get("ip") or "").strip())
        return web.json_response({"ok": True})

    async def keymap(_):
        return web.json_response(app.keymap())

    async def set_keycode(req):
        try:
            await app.set_keycode(await req.json())
        except (ValueError, KeyError, TypeError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def vial_get(req):
        try:
            return web.json_response(await app.vial_state(reload=req.query.get("reload") == "1"))
        except (ValueError, OSError) as e:
            return web.json_response({"connected": False, "error": str(e)})

    async def vial_status(_):
        return web.json_response(app.unlock)

    def vial_action(fn):
        async def handler(req):
            try:
                await fn(req)
            except (ValueError, KeyError, TypeError, OSError) as e:
                return web.json_response({"ok": False, "error": str(e)}, status=400)
            return web.json_response({"ok": True})
        return handler

    async def _unlock(_): await app.vial_unlock()
    async def _lock(_): await app.vial_lock()
    async def _set(req): await app.vial_set(req.match_info["kind"], await req.json())

    async def backup(_):
        try:
            return web.json_response(await app.pad_backup())
        except (ValueError, OSError) as e:
            return web.json_response({"error": str(e)}, status=400)

    async def restore(req):
        try:
            return web.json_response(dict(await app.pad_restore(await req.json()), ok=True))
        except (ValueError, KeyError, TypeError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def pad_layer(req):
        try:
            await app.set_pad_layer((await req.json())["layer"])
        except (ValueError, KeyError, TypeError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def test_steps(req):
        try:
            body = await req.json()
            steps = body["steps"]
            if not isinstance(steps, list):
                raise ValueError("steps must be a list")
            app.engine.test_steps(steps, body.get("src"))
        except (ValueError, KeyError, TypeError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def test_key(req):
        try:
            body = await req.json()
            layer, wm = int(body["layer"]), int(body["wm"])
            app.engine.test_key(layer, wm, app.key_index(layer, wm))
        except (ValueError, KeyError, TypeError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def ws(req):
        """Pushes status, LED preview and new pad events about 10x a second."""
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(req)
        last, last_t = None, 0.0

        async def reader():
            async for msg in sock:
                if msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        rt = asyncio.create_task(reader())
        try:
            while not sock.closed and not rt.done():
                st = _status(app)
                st["leds"] = app.leds.last if app.leds else None
                events = [e for e in app.engine.log if e["t"] > last_t]
                if events:
                    last_t = events[-1]["t"]
                if st != last or events:
                    await sock.send_json(dict(st, events=events))
                    last = st
                await asyncio.sleep(0.1)
        except (ConnectionResetError, RuntimeError):
            pass
        finally:
            rt.cancel()
        return sock

    @web.middleware
    async def revalidate(req, handler):
        """Make browsers re-check UI files on every load (cheap 304s), so updates show on refresh."""
        resp = await handler(req)
        if req.path == "/" or req.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    wa = web.Application(middlewares=[revalidate])
    wa.add_routes([
        web.get("/", index), web.static("/static", STATIC),
        web.get("/api/status", status), web.get("/api/ws", ws),
        web.get("/api/config", get_config), web.put("/api/config", put_config),
        web.get("/api/strips", strips), web.get("/api/pad", pad_keys),
        web.get("/api/fx", fx_list),
        web.get("/api/scan", scan), web.get("/api/params", params), web.post("/api/console", set_console),
        web.get("/api/keymap", keymap), web.post("/api/keymap", set_keycode),
        web.post("/api/pad/layer", pad_layer), web.post("/api/test/steps", test_steps), web.post("/api/test/key", test_key), web.get("/api/pad/backup", backup), web.post("/api/pad/restore", restore),
        web.get("/api/vial", vial_get), web.get("/api/vial/unlock", vial_status),
        web.post("/api/vial/unlock", vial_action(_unlock)), web.post("/api/vial/lock", vial_action(_lock)),
        web.post("/api/vial/{kind}", vial_action(_set)),
    ])
    runner = web.AppRunner(wa, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
