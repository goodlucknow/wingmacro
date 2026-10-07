"""Walk the console parameter tree via node definitions (one instance of each repeated node).
Usage: python tools/walk_tree.py OUT.jsonl [console-ip]"""
import asyncio, json, re, sys, time
sys.path.insert(0, "/workspace/wingmacro/app")
from wingmacro.wing import Wing
OUT = sys.argv[1]
async def go():
    w = Wing(sys.argv[2] if len(sys.argv) > 2 else "10.0.1.8"); t = asyncio.create_task(w.run()); await w.wait_connected()
    fo = open(OUT, "w"); leaves = set(); nodes = 0; queue = ["/"]; visited = set(); t0 = time.time()
    while queue:
        path = queue.pop(0)
        if path in visited: continue
        visited.add(path)
        defs = await w.defs(path, timeout=3)
        nodes += 1
        seen_num = False
        for d in defs:
            if not d.name: continue
            child = path.rstrip("/") + "/" + d.name
            if d.type == 0:
                fo.write(json.dumps({"node": "/".join("N" if re.fullmatch(r"\d+", x) else x for x in child.split("/"))}) + "\n")
                if re.fullmatch(r"\d+", d.name):
                    if seen_num: continue          # only expand the first of repeated numbered nodes
                    seen_num = True
                queue.append(child)
            else:
                norm = "/".join("N" if re.fullmatch(r"\d+", s) else s for s in child.split("/"))
                if norm in leaves: continue
                leaves.add(norm)
                fo.write(json.dumps({"path": norm, "type": d.type_name, "unit": d.unit, "ro": d.readonly, "long": d.longname,
                                "min": d.min, "max": d.max, "items": d.items[:12], "example": child}) + "\n"); fo.flush()
    print(f"{nodes} nodes, {len(leaves)} leaf params in {time.time()-t0:.1f}s")
    fo.close()
    t.cancel()
asyncio.run(go())
