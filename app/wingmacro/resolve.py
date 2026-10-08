"""Find a parameter again after the node's model changed (an FX slot or insert loaded with another effect).

A mapped step remembers what was picked (`pref`: path, model, key, longname, unit, type, idx). When the
node's current model lacks that key, the equivalent is looked up in this order:
same key -> alias role (below) -> same long name and unit -> same position (what the WING itself does
with its own controls) -> nothing. Every match must be type-compatible: a number never drives an option list.
Roles come from `docs/wing-fx-models-3.1.1.json` (every model's definitions on fw 3.1.1).
"""
from . import wing as W

ROLES = [
    ("feed", "rep", "fb", "sust"),   # feedback / repeats / sustain
    ("time", "dly"),                 # delay time
    ("pdel",),                       # pre-delay
    ("dcy",),                        # decay
    ("fact",),                       # delay factor / subdivision
    ("mspd", "mod"),                 # reverb modulation speed
    ("mult", "lmult"),               # bass / low multiplier
    ("lc", "rlc"),                   # low cut
    ("hc",),
    ("flc",), ("fhc",),              # feedback low / high cut
    ("sprd",), ("size",), ("damp",), ("diff",), ("spin",),
]
ROLE = {k: r for r in ROLES for k in r}

NUMERIC = {W.T_LINF, W.T_LOGF, W.T_FADER, W.T_INT}
CHOICE = {W.T_ENUM, W.T_FENUM}


def _kind(t):
    return "num" if t in NUMERIC else "choice" if t in CHOICE else None


def compatible(d, ptype=None):
    """`d` can be stepped/set where a param of type `ptype` (None = unknown) was picked."""
    if d is None or d.readonly or _kind(d.type) is None:
        return False
    return ptype is None or _kind(d.type) == _kind(ptype)


def pref_of(path, model, d):
    """What to remember about a picked param, to find it again in another model."""
    return {"path": path, "model": model, "key": d.name, "longname": d.longname, "unit": d.unit,
            "type": d.type_name, "idx": d.idx}


def type_code(name):
    try:
        return ["node", "linf", "logf", "fader", "int", "enum", "fenum", "str"].index(name)
    except ValueError:
        return None


def match(key, pref, defs):
    """The NodeDef in `defs` ({name: NodeDef}, the node's current model) that stands for `key`
    (picked as `pref`, may be None), or None. Returns (def, how): how = key | role | name | position."""
    ptype = type_code(pref["type"]) if pref and pref.get("type") else None
    d = defs.get(key)
    if compatible(d, ptype):
        return d, "key"
    for k in ROLE.get(key, ()):
        if k != key and compatible(defs.get(k), ptype):
            return defs[k], "role"
    if not pref:
        return None, None
    ln = (pref.get("longname") or "").upper()
    if ln:
        for d in defs.values():
            if d.longname.upper() == ln and d.unit == pref.get("unit", "") and compatible(d, ptype):
                return d, "name"
    idx = pref.get("idx")
    if idx is not None:
        for d in defs.values():
            if d.idx == idx and d.name != "mdl" and compatible(d, ptype):
                return d, "position"
    return None, None
