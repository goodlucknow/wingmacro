"""Config file: JSON, schema in docs/config-model.md."""
import json
import os
import sys
from pathlib import Path

DEFAULT = {
    "version": 5,
    "console": {"ip": "", "discover": True},
    "pad": {"background": [22, 255, 47], "cancel_ms": 400, "hold_ms": 800},
    "macros": {},
    "layers": {"0": {"buttons": {}, "encoders": {}}},
}

PALETTE = {  # keep in sync with static/app.js
    # the WING's 12 colours in its picker order (1-12), tuned for the pad's LEDs: orange = the case/UI amber
    "steel": (150, 160, 200),
    "sky": (140, 255, 200),
    "indigo": (178, 255, 200),
    "teal": (128, 255, 200),
    "green": (85, 255, 200),
    "olive": (55, 255, 200),
    "yellow": (40, 255, 200),
    "orange": (22, 255, 200),
    "red": (0, 255, 200),
    "coral": (5, 150, 200),
    "magenta": (213, 255, 200),
    "purple": (192, 255, 200),
    "white": (0, 0, 200), "off": (0, 0, 0),
    # older names, still accepted
    "crimson": (0, 255, 200), "amber": (22, 255, 200), "cyan": (128, 255, 200), "blue": (170, 255, 200),
}


def default_path():
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "wingmacro" / "wingmacro.json"


def load(path):
    path = Path(path)
    if not path.exists():
        save(path, DEFAULT)
    cfg = json.loads(path.read_text())
    if migrate(cfg):
        save(path, cfg)  # previous file kept as .json.bak
    validate(cfg)
    return cfg


def _as_steps(do):
    return [{"do": "macro", "name": do}] if isinstance(do, str) else list(do or [])


def _migrate_mapping(b):
    """v1 -> v2: `do` was a step list, a macro name, or {"toggle": [A, B]}. Now `do` is always a step
    list; toggling is the mapping's own (`toggle`, with `off` or an automatic reverse)."""
    do = b.get("do")
    if isinstance(do, dict) and "toggle" in do:
        on, off = (list(do["toggle"]) + [[], []])[:2]
        b.update(do=_as_steps(on), off=_as_steps(off), toggle=True, off_auto=False)
    else:
        b["do"] = _as_steps(do)
    b.pop("led", None)
    steps = b["do"]
    if (not b.get("toggle") and b.get("trigger") != "momentary" and len(steps) == 1
            and steps[0].get("do") in ("mute", "mgrp", "softmute") and steps[0].get("op", "toggle") == "toggle"):
        b.update(do=[dict(steps[0], op="down" if steps[0]["do"] == "softmute" else "on")], toggle=True, off_auto=True)


def _split_softmute(steps):
    """v2 -> v3: the old soft mute = a timed fader fade plus a mute; now two console actions."""
    out = []
    for st in steps or []:
        if st.get("do") != "softmute":
            out.append(st)
            continue
        fade = {"do": "fade", "target": st.get("target"), "time": st.get("time", 5)}
        if st.get("op") == "up":
            out += [{"do": "mute", "target": st.get("target"), "op": "off"}, dict(fade, db=0)]
        else:
            out += [dict(fade, db="-inf"), {"do": "mute", "target": st.get("target"), "op": "on"}]
    return out


_INVERSE_OPS = {"mute": {"on": "off", "off": "on"}, "mgrp": {"on": "off", "off": "on"}}


def _auto_off(steps):
    """The automatic Off list toggle keys had up to v3 (the On list reversed: mutes and mute groups
    flipped, fades sent back, key colours restored). Kept only to write it out during migration."""
    out = []
    for s in reversed(steps):
        d = s.get("do")
        if d in _INVERSE_OPS and s.get("op") in _INVERSE_OPS[d]:
            out.append(dict(s, op=_INVERSE_OPS[d][s["op"]]))
        elif d == "fade" and s.get("db") != "back":
            out.append(dict(s, db="back"))
        elif d == "led":
            out.append({k: v for k, v in s.items() if k in ("do", "layer", "key")} | {"colour": "base"})
    return out


def _mappings(cfg):
    for layer in cfg.get("layers", {}).values():
        yield from layer.get("buttons", {}).values()
        yield from (e["push"] for e in layer.get("encoders", {}).values() if "push" in e)


def _key_mode_v5(m):
    """v4 -> v5: trigger (press | hold | momentary) + toggle -> mode (single | toggle | momentary) + hold."""
    trig = m.pop("trigger", "press")
    toggle = m.pop("toggle", False)
    if trig == "momentary":
        m["mode"] = "momentary"
        m.setdefault("off", _auto_off(m.get("do", [])))  # the old release put things back by itself
    else:
        m["mode"] = "toggle" if toggle else "single"
        if trig == "hold":
            m["hold"] = True
    if m["mode"] == "single":
        m.pop("off", None)


def _steps_v5(steps, rotary):
    """v4 -> v5: FX actions become parameter actions; the cycle actions become a knob's Parameter
    or a key's Set parameter (next/previous, wrapping as cycle did)."""
    out = []
    for st in steps or []:
        d = st.get("do")
        if d in ("fx", "fx_cycle", "fx_set"):
            st = {k: v for k, v in st.items() if k not in ("slot", "param")} | {"path": f"/fx/{st.get('slot')}/{st.get('param')}"}
            d = {"fx": "param", "fx_cycle": "param_cycle", "fx_set": "param_set"}[d]
            st["do"] = d
        if d == "param_cycle":
            if rotary:
                st = {k: v for k, v in st.items() if k != "dir"} | {"do": "param"}
            else:
                st = {k: v for k, v in st.items() if k != "dir"} | {
                    "do": "param_set", "op": "dec" if st.get("dir") == "prev" else "inc", "wrap": True}
        out.append(st)
    return out


def migrate(cfg):
    changed = _migrate_v1(cfg)
    if cfg.get("version", 1) < 3:
        lists = []
        for layer in cfg.get("layers", {}).values():
            maps = list(layer.get("buttons", {}).values()) + [e["push"] for e in layer.get("encoders", {}).values() if "push" in e]
            lists += [(m, k) for m in maps for k in ("do", "off") if k in m]
        lists += [(m, "steps") for m in cfg.get("macros", {}).values()]
        for owner, key in lists:
            owner[key] = _split_softmute(owner[key])
        cfg["version"] = 3
        changed = True
    if cfg.get("version", 1) < 4:
        # v3 -> v4: no automatic Off. Toggle keys that used it get it written out as their Off list.
        for m in _mappings(cfg):
            if m.pop("off_auto", True) is not False and m.get("toggle"):  # v3 default was automatic
                m["off"] = _auto_off(m.get("do", []))
        cfg["version"] = 4
        changed = True
    if cfg.get("version", 1) < 5:
        for m in _mappings(cfg):
            _key_mode_v5(m)
            for k in ("do", "off"):
                if k in m:
                    m[k] = _steps_v5(m[k], False)
        for layer in cfg.get("layers", {}).values():
            for e in layer.get("encoders", {}).values():
                for k in ("turn", "push_turn"):
                    if k in e:
                        e[k] = _steps_v5(e[k], True)
        for mac in cfg.get("macros", {}).values():
            mac["steps"] = _steps_v5(mac.get("steps"), False)
        cfg["version"] = 5
        changed = True
    return changed


def _migrate_v1(cfg):
    if cfg.get("version", 1) >= 2:
        return False
    for layer in cfg.get("layers", {}).values():
        for b in layer.get("buttons", {}).values():
            _migrate_mapping(b)
        for e in layer.get("encoders", {}).values():
            if "push" in e:
                _migrate_mapping(e["push"])
    for m in cfg.get("macros", {}).values():
        m.pop("retrigger", None)
    cfg["version"] = 2
    return True


def save(path, cfg):
    """Atomic write, keeping the previous file as .bak."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    if path.exists():
        os.replace(path, path.with_suffix(".json.bak"))
    os.replace(tmp, path)


def validate(cfg):
    """Raise ValueError with a readable message for structural problems."""
    from .actions import ACTIONS

    def check_steps(steps, where):
        if not isinstance(steps, list):
            raise ValueError(f"{where}: actions must be a list")
        for i, st in enumerate(steps):
            if st.get("do") not in ACTIONS:
                raise ValueError(f"{where} step {i + 1}: unknown action {st.get('do')!r}")
            if st["do"] == "macro" and st.get("name") not in cfg.get("macros", {}):
                raise ValueError(f"{where} step {i + 1}: unknown macro {st.get('name')!r}")

    def check_button(b, where):
        if b.get("trigger", "press") not in ("press", "hold", "momentary"):
            raise ValueError(f"{where}: trigger must be press, hold or momentary")
        check_steps(b.get("do", []), where)
        check_steps(b.get("off", []), where + " (off)")

    if not isinstance(cfg, dict) or not isinstance(cfg.get("layers"), dict):
        raise ValueError("config needs a 'layers' object")
    for name, m in cfg.get("macros", {}).items():
        check_steps(m.get("steps", []), f"macro {name}")
    for ln, layer in cfg["layers"].items():
        if ln not in ("0", "1", "2", "3"):
            raise ValueError(f"layer {ln!r}: must be 0-3")
        for wm, b in layer.get("buttons", {}).items():
            if not wm.isdigit() or not 1 <= int(wm) <= 32:
                raise ValueError(f"layer {ln} button {wm!r}: WM id must be 1-32")
            check_button(b, f"layer {ln} WM{wm}")
        for knob, e in layer.get("encoders", {}).items():
            if knob not in ("left", "right"):
                raise ValueError(f"layer {ln} encoder {knob!r}: must be left or right")
            for k in ("turn", "push_turn"):
                check_steps(e.get(k, []), f"layer {ln} {knob} {k}")
            if "push" in e:
                check_button(e["push"], f"layer {ln} {knob} push")


def colour(c, default=(0, 0, 0)):
    if c is None:
        return default
    if isinstance(c, str):
        return PALETTE.get(c, default)
    return tuple(c)
