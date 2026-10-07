"""Compare doc paths (doc_paths.json) with the console tree (tree.jsonl) in DIR. Writes DIR/compare.md.
Usage: python tools/compare_tree.py DIR"""
import json, sys, collections
S = sys.argv[1]
doc = set(json.load(open(f"{S}/doc_paths.json")))
con_leaf, con_node = {}, set()
for line in open(f"{S}/tree.jsonl"):
    r = json.loads(line)
    if "node" in r: con_node.add(r["node"])
    else: con_leaf[r["path"]] = r
con = set(con_leaf) | con_node
both = doc & con; only_doc = sorted(doc - con); only_con = sorted(set(con_leaf) - doc)
def top(p): return "/".join(p.split("/")[:2])
def grouped(paths):
    g = collections.defaultdict(list)
    for p in paths: g[top(p)].append(p)
    return g
out = [f"# WING docs vs console tree\n",
       f"- doc paths: {len(doc)}; console: {len(con_leaf)} params + {len(con_node)} nodes",
       f"- in both: {len(both)}; doc only: {len(only_doc)}; console-only params: {len(only_con)}\n"]
for title, lst in (("Doc only (not on console)", only_doc), ("Console only (undocumented params)", only_con)):
    out.append(f"## {title}\n")
    for k, v in sorted(grouped(lst).items()):
        out.append(f"### {k} ({len(v)})\n")
        for p in v:
            r = con_leaf.get(p)
            out.append(f"- `{p}`" + (f" — {r['type']}{' ro' if r['ro'] else ''} {r['unit']} {r['long']}".rstrip() if r else ""))
        out.append("")
open(f"{S}/compare.md", "w").write("\n".join(out))
print("\n".join(out[1:3]))
for title, lst in (("doc-only", only_doc), ("con-only", only_con)):
    print(title, {k: len(v) for k, v in sorted(grouped(lst).items())})
