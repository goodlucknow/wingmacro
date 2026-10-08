"""Human-readable names for the console's parameter tree.

The tree itself always comes from the console (0xdd definitions). This table only makes it
readable: friendly names for known nodes and parameters, falling back to the console's long
name, then to the raw key. Anything new in a WING firmware update still shows up."""
import re

# Node labels by key (the last path segment, or a relative path like "in/set").
NODE_LABELS = {
    "in": "Input", "in/set": "Input settings", "in/conn": "Input routing", "flt": "Filters",
    "peq": "Pre-EQ", "eq": "EQ", "gate": "Gate", "gatesc": "Gate sidechain", "dyn": "Dynamics",
    "dynsc": "Dynamics sidechain", "dynxo": "Dynamics crossover", "preins": "Pre insert",
    "postins": "Post insert", "send": "Sends", "main": "Main sends", "talk": "Talkback",
}
TOP_LABELS = {
    "ch": "Channels", "aux": "Aux inputs", "bus": "Buses", "main": "Mains", "mtx": "Matrices",
    "dca": "DCAs", "fx": "Effects", "mgrp": "Mute groups", "cfg": "Setup", "io": "I/O",
    "cards": "Expansion cards", "play": "Player", "rec": "Recorder", "$ctl": "Control surface",
    "$stat": "Status", "$syscfg": "System", "$globals": "Globals",
}
TOP_ORDER = list(TOP_LABELS)
# Strip-level groups in this order first; anything else the console has follows.
NODE_ORDER = ["in", "flt", "gate", "gatesc", "eq", "peq", "dyn", "dynsc", "dynxo",
              "preins", "postins", "send", "main"]

PARAM_LABELS = {
    "fdr": "Fader", "mute": "Mute", "pan": "Pan", "wid": "Width", "lvl": "Level", "on": "On",
    "mdl": "Model", "mix": "Mix", "thr": "Threshold", "att": "Attack", "hld": "Hold",
    "rel": "Release", "ratio": "Ratio", "knee": "Knee", "det": "Detector", "env": "Envelope",
    "auto": "Auto", "gain": "Gain", "range": "Range", "acc": "Accent", "lc": "Low cut on",
    "lcf": "Low cut freq", "lcs": "Low cut slope", "hc": "High cut on", "hcf": "High cut freq",
    "hcs": "High cut slope", "tilt": "Tilt", "tf": "Tool filter on", "trim": "Trim",
    "bal": "Balance", "inv": "Phase invert", "pon": "Pre", "pre": "Pre", "mode": "Mode",
    "plink": "Pan link", "col": "Colour", "name": "Name", "icon": "Icon", "led": "LED",
    "mon": "Monitor bus", "solosafe": "Solo safe", "proc": "Processing order", "ptap": "Tap point",
    "f": "Frequency", "q": "Q", "src": "Source", "tap": "Tap point", "type": "Filter type",
    "depth": "Depth", "dly": "Delay", "dlyon": "Delay on", "dlymode": "Delay mode",
    "ins": "Insert FX", "w": "Weight", "clink": "Custom link", "fxmix": "FX mix",
    "srcauto": "Auto switch to alt", "altsrc": "Use alt input", "tapwid": "Tap width",
}
ON_LABELS = {"eq": "EQ on", "peq": "Pre-EQ on", "gate": "Gate on", "dyn": "Dynamics on",
             "send": "Send on", "main": "Send on", "preins": "Insert on", "postins": "Insert on"}
MDL_LABELS = {"flt": "Tool filter type"}
BAND = re.compile(r"([1-9]|l|h)(g|f|q|eq)")
BAND_PART = {"g": "gain", "f": "freq", "q": "Q", "eq": "shelf type"}
KEEP_CAPS = {"EQ", "LC", "HC", "SC", "FX", "XO", "DLY", "ALT", "MON", "LED", "SOF", "DCA", "USB",
             "MIDI", "OSC", "RTA", "PFL", "AFL", "LR", "MS", "ID", "IP", "DAW"}


def tidy(longname):
    """'LC FREQ' -> 'LC freq': sentence case, known abbreviations kept."""
    words = longname.replace("_", " ").split()
    out = [w if w in KEEP_CAPS else w.lower() for w in words]
    out = [w if len(w) == 1 else o for w, o in zip(words, out)]  # "ECHO L" -> "Echo L"
    if out and out[0] not in KEEP_CAPS:
        out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


def _groups(path):
    """Path segments with numbers dropped: /ch/3/send/MX1/on -> ['ch', 'send', 'MX1', 'on']."""
    return [s for s in path.strip("/").split("/") if not s.isdigit()]


def node_label(path, longname=""):
    segs = path.strip("/").split("/")
    if len(segs) == 1 and segs[0] in TOP_LABELS:
        return TOP_LABELS[segs[0]]
    for k in ("/".join(segs[-2:]), segs[-1]):
        if k in NODE_LABELS:
            return NODE_LABELS[k]
    return tidy(longname) if longname else segs[-1]


def param_label(path, longname=""):
    name = path.rstrip("/").rpartition("/")[2]
    if path.strip("/").startswith("fx/") and name not in ("mdl", "fxmix"):
        return tidy(longname) if longname else name  # FX params differ per model: trust the console
    parent = (_groups(path)[-2:-1] or [""])[0]
    if parent.startswith("MX") or parent.isdigit():
        parent = "send"
    if name == "on" and parent in ON_LABELS:
        return ON_LABELS[parent]
    if name == "mdl" and parent in MDL_LABELS:
        return MDL_LABELS[parent]
    m = BAND.fullmatch(name)
    if m and parent in ("eq", "peq"):
        band = {"l": "Low", "h": "High"}.get(m[1], f"Band {m[1]}")
        return f"{band} {BAND_PART[m[2]]}"
    if name in PARAM_LABELS:
        return PARAM_LABELS[name]
    return tidy(longname) if longname else name


def node_sort_key(name, top=False):
    if top:
        return (TOP_ORDER.index(name) if name in TOP_ORDER else len(TOP_ORDER), name)
    if name.isdigit():
        return (0, int(name), "")
    return (1, NODE_ORDER.index(name) if name in NODE_ORDER else len(NODE_ORDER), name)
