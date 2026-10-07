"""Vial keystroke macros <-> the pad's macro buffer (format: vial-qmk dynamic_keymap.c).

A macro is a list of actions: {"text": "abc"}, {"tap"|"down"|"up": [keycodes]}, {"delay": ms}.
Macros are stored back to back, each terminated by a 0 byte.
"""
SS_PREFIX, SS_TAP, SS_DOWN, SS_UP, SS_DELAY = 1, 1, 2, 3, 4
EXT = {"tap": 5, "down": 6, "up": 7}
BASIC = {"tap": SS_TAP, "down": SS_DOWN, "up": SS_UP}


def _enc_kc(kc):
    """16-bit keycode as two non-zero bytes, little-endian (0xXX00 is sent as 0xFFXX)."""
    if kc & 0xFF == 0:
        kc = 0xFF00 | (kc >> 8)
    return bytes([kc & 0xFF, kc >> 8])


def encode(macros):
    out = bytearray()
    for actions in macros:
        for a in actions:
            if "text" in a:
                out += bytes(b for b in a["text"].encode("ascii", "ignore") if b >= 0x20 or b in (9, 10))
            elif "delay" in a:
                ms = max(0, min(int(a["delay"]), 254 * 255 + 254))
                out += bytes([SS_PREFIX, SS_DELAY, ms % 255 + 1, ms // 255 + 1])
            else:
                kind = next(k for k in ("tap", "down", "up") if k in a)
                for kc in a[kind]:
                    if 0 < kc <= 0xFF:
                        out += bytes([SS_PREFIX, BASIC[kind], kc])
                    else:
                        out += bytes([SS_PREFIX, EXT[kind]]) + _enc_kc(kc)
        out.append(0)
    return bytes(out)


def decode(buf, count):
    macros, cur, i = [], [], 0

    def add(kind, kc):
        if cur and kind in cur[-1] and kind != "text":
            cur[-1][kind].append(kc)
        else:
            cur.append({kind: [kc]})

    while i < len(buf) and len(macros) < count:
        b = buf[i]
        if b == 0:
            macros.append(cur)
            cur = []
            i += 1
        elif b == SS_PREFIX and i + 1 < len(buf):
            code = buf[i + 1]
            if code in (SS_TAP, SS_DOWN, SS_UP):
                add({SS_TAP: "tap", SS_DOWN: "down", SS_UP: "up"}[code], buf[i + 2])
                i += 3
            elif code in (5, 6, 7):
                kc = buf[i + 2] | buf[i + 3] << 8
                if kc > 0xFF00:
                    kc = (kc & 0xFF) << 8
                add({5: "tap", 6: "down", 7: "up"}[code], kc)
                i += 4
            elif code == SS_DELAY:
                cur.append({"delay": (buf[i + 2] - 1) + (buf[i + 3] - 1) * 255})
                i += 4
            else:
                i += 2
        else:
            if cur and "text" in cur[-1]:
                cur[-1]["text"] += chr(b)
            else:
                cur.append({"text": chr(b)})
            i += 1
    while len(macros) < count:
        macros.append([])
    return macros
