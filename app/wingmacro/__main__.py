"""wingmacro: control a Behringer WING from a DOIO KB16 pad.

  python -m wingmacro tray [...]   # with a tray / menu-bar icon (the default in the packaged apps)
  python -m wingmacro [run] [--config PATH] [--wing IP] [--web-host H] [--web-port N] [--no-pad]
  python -m wingmacro discover
  python -m wingmacro fx SLOT [--wing IP]     # list a slot's parameters as the console reports them
"""
import argparse
import asyncio
import logging
import sys

from . import config as C
from .wing import Wing, discover


def main():
    ap = argparse.ArgumentParser(prog="wingmacro")
    packaged = getattr(sys, "frozen", False)
    ap.add_argument("cmd", nargs="?", default="tray" if packaged else "run", choices=["run", "tray", "discover", "fx"])
    ap.add_argument("slot", nargs="?", type=int)
    ap.add_argument("--config", default=str(C.default_path()))
    ap.add_argument("--wing", help="console IP (default: config, then discovery)")
    ap.add_argument("--web-host", default="127.0.0.1", help="0.0.0.0 to reach the UI from other machines")
    ap.add_argument("--web-port", type=int, default=8780)
    ap.add_argument("--no-pad", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.cmd == "tray":
        from . import tray
        tray.setup_logging(a.config, a.verbose)
        tray.run(a.config, a.wing, not a.no_pad, a.web_host, a.web_port)
        return
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "discover":
        for w in discover(host=a.wing or "255.255.255.255"):
            print(f"{w['ip']}  {w['name']}  {w['model']}  fw {w['firmware']}")
    elif a.cmd == "fx":
        asyncio.run(_fx(a.wing, a.slot or 1))
    else:
        from .main import App
        print(f"config: {a.config}\nweb UI: http://{a.web_host}:{a.web_port}/")
        asyncio.run(App(a.config, a.wing, not a.no_pad).run(a.web_host, a.web_port))


async def _fx(ip, slot):
    w = Wing(ip)
    task = asyncio.create_task(w.run())
    await asyncio.wait_for(w.wait_connected(), 10)
    print(f"fx {slot}: {await w.get(f'/fx/{slot}/mdl')}")
    for d in await w.defs(f"/fx/{slot}"):
        if d.type:
            rng = d.items if d.items else (d.min, d.max)
            print(f"  {d.name:8} {d.type_name:5} {d.unit:3} {rng}{'  [ro]' if d.readonly else ''}")
    task.cancel()


if __name__ == "__main__":
    main()
