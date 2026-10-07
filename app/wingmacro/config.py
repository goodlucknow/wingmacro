"""Config file: JSON, schema in docs/config-model.md."""
import json
import os
import sys
from pathlib import Path

DEFAULT = {
    "version": 1,
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
    validate(cfg)
    return cfg


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

    def steps_of(do, where):
        if isinstance(do, str):
            if do not in cfg.get("macros", {}):
                raise ValueError(f"{where}: unknown macro {do!r}")
            return []
        if isinstance(do, dict) and "toggle" in do:
            if len(do["toggle"]) != 2:
                raise ValueError(f"{where}: toggle needs two macros")
            return [s for d in do["toggle"] for s in steps_of(d, where)]
        if isinstance(do, list):
            return do
        raise ValueError(f"{where}: 'do' must be a macro name, a step list or a toggle")

    def check_steps(steps, where):
        for i, st in enumerate(steps):
            if st.get("do") not in ACTIONS:
                raise ValueError(f"{where} step {i + 1}: unknown action {st.get('do')!r}")

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
            if b.get("trigger", "press") not in ("press", "hold", "momentary"):
                raise ValueError(f"layer {ln} WM{wm}: trigger must be press, hold or momentary")
            check_steps(steps_of(b.get("do", []), f"layer {ln} WM{wm}"), f"layer {ln} WM{wm}")
        for knob, e in layer.get("encoders", {}).items():
            if knob not in ("left", "right"):
                raise ValueError(f"layer {ln} encoder {knob!r}: must be left or right")
            for k in ("turn", "push_turn"):
                check_steps(e.get(k, []), f"layer {ln} {knob} {k}")
            if "push" in e:
                check_steps(steps_of(e["push"].get("do", []), f"layer {ln} {knob} push"),
                            f"layer {ln} {knob} push")


def colour(c, default=(0, 0, 0)):
    if c is None:
        return default
    if isinstance(c, str):
        return PALETTE.get(c, default)
    return tuple(c)
