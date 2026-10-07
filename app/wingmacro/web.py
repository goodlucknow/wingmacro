"""Minimal local web UI: status, recent pad events, and a JSON config editor."""
import json
from pathlib import Path

from aiohttp import web

STATIC = Path(__file__).parent / "static"


async def start_web(app, host, port):
    async def index(_):
        return web.FileResponse(STATIC / "index.html")

    async def status(_):
        w, p = app.wing, app.pad
        return web.json_response({
            "wing": {"connected": w.connected, "host": w.host, "info": w.info},
            "pad": {"connected": bool(p and p.connected), "layer": app.engine.layer},
            "fx": {k: v for k, v in app.ctx.fx_models.items() if v and v != "NONE"},
            "events": app.engine.log[-20:],
            "tap_ms": app.ctx.tap_ms,
        })

    async def get_config(_):
        return web.json_response(app.cfg)

    async def put_config(req):
        try:
            cfg = json.loads(await req.text())
            await app.apply_config(cfg)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def fx_params(req):
        slot = int(req.match_info["slot"])
        defs = await app.wing.defs(f"/fx/{slot}")
        return web.json_response([
            {"name": d.name, "longname": d.longname, "type": d.type_name, "unit": d.unit,
             "min": d.min, "max": d.max, "items": d.items, "readonly": d.readonly}
            for d in defs if d.type != 0])

    wa = web.Application()
    wa.add_routes([
        web.get("/", index), web.get("/api/status", status),
        web.get("/api/config", get_config), web.put("/api/config", put_config),
        web.get("/api/fx/{slot}", fx_params),
    ])
    runner = web.AppRunner(wa, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
