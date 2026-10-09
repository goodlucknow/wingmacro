"""Headless-Chrome screenshot of the running UI (port 8780) for a temporary test macro; restores the config after.
Needs chrome-headless-shell (playwright cache) + LD_LIBRARY_PATH with libatk etc. Edit main() per test; PNGs land next to this file."""
import asyncio, base64, json, subprocess, sys, urllib.request, os, copy
sys.path.insert(0, "/workspace/wingmacro/app")
import aiohttp
from wingmacro.wing import Wing
API = "http://localhost:8780"; SP = os.path.dirname(__file__)
CH = os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell")
def req(path, body=None, method="GET"):
    r = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None,
                               {"Content-Type": "application/json"}, method=method)
    return json.load(urllib.request.urlopen(r))

async def shot(name, js):
    p = subprocess.Popen([CH, "--remote-debugging-port=9333", "--window-size=1300,900", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        await asyncio.sleep(1.5)
        async with aiohttp.ClientSession() as s:
            tabs = await (await s.get("http://127.0.0.1:9333/json")).json()
            ws = await s.ws_connect(tabs[0]["webSocketDebuggerUrl"], max_msg_size=0)
            n = 0
            async def call(m, **pa):
                nonlocal n; n += 1; await ws.send_json({"id": n, "method": m, "params": pa})
                while True:
                    r = await ws.receive_json()
                    if r.get("id") == n: return r.get("result")
            await call("Page.enable"); await call("Page.navigate", url=API + "/"); await asyncio.sleep(3)
            await call("Runtime.evaluate", expression=js); await asyncio.sleep(2)
            txt = await call("Runtime.evaluate", expression="document.querySelector('.hint.na, .step .hint')?.textContent || ''")
            r = await call("Page.captureScreenshot", format="png")
            open(f"{SP}/{name}.png", "wb").write(base64.b64decode(r["data"]))
            return txt["result"].get("value")
    finally:
        p.kill()

async def main():
    w = Wing("10.0.1.8"); asyncio.create_task(w.run()); await w.wait_connected()
    assert await w.get("/fx/8/mdl") == "NONE"
    orig = req("/api/config")
    try:
        await w.set("/fx/8/mdl", "TAP-DL"); await asyncio.sleep(1)
        cfg = copy.deepcopy(orig)
        cfg.setdefault("macros", {})["zz test"] = {"steps": [{"do": "param_set", "path": "/fx/8/rep", "op": "inc", "plabel": "Repeats"}]}
        print(req("/api/config", cfg, "PUT"))
        print("stamped:", req("/api/config")["macros"]["zz test"]["steps"][0].get("pref"))
        js = "S.macroSel='zz test'; go('macros');"
        for m in ("ST-DL", "BODY"):
            await w.set("/fx/8/mdl", m); await asyncio.sleep(1.5)
            print(m, req("/api/resolve?path=/fx/8/rep"), "| UI:", await shot(m.replace("/", ""), js))
    finally:
        req("/api/config", orig, "PUT")
        await w.set("/fx/8/mdl", "NONE"); await asyncio.sleep(0.5)
        print("restored", await w.get("/fx/8/mdl"), "zz test" in req("/api/config").get("macros", {}))
asyncio.run(main())
