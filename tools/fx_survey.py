"""Dump every FX model's 0xdd defs to docs/wing-fx-models-3.1.1.json, using EMPTY slot 8 (checked, restored to NONE).
Run: .venv/bin/python tools/fx_survey.py  (update the output name for a new firmware)."""
import asyncio, json, sys
sys.path.insert(0, "/workspace/wingmacro/app")
from wingmacro.wing import Wing
SLOT = 8
async def main():
    w = Wing("10.0.1.8"); t = asyncio.create_task(w.run()); await w.wait_connected()
    mdls = {}
    for s in range(1, 17):
        mdls[s] = await w.get(f"/fx/{s}/mdl")
    print(mdls)
    if mdls[SLOT] != "NONE":
        print("slot not empty"); return
    md = {d.name: d for d in await w.defs(f"/fx/{SLOT}")}["mdl"]
    out = {}
    try:
        for m in md.items:
            if m == "NONE": continue
            await w.set(f"/fx/{SLOT}/mdl", m); await asyncio.sleep(0.6)
            got = await w.get(f"/fx/{SLOT}/mdl")
            defs = await w.defs(f"/fx/{SLOT}")
            out[m] = [dict(name=d.name, longname=d.longname, type=d.type_name, unit=d.unit, ro=d.readonly,
                           min=d.min, max=d.max, steps=d.steps, items=d.items, idx=d.idx) for d in defs]
            print(m, got, len(defs))
    finally:
        await w.set(f"/fx/{SLOT}/mdl", "NONE"); await asyncio.sleep(0.5)
        print("restored", await w.get(f"/fx/{SLOT}/mdl"))
    json.dump(out, open("/workspace/wingmacro/docs/wing-fx-models-3.1.1.json", "w"), indent=1)
asyncio.run(main())
