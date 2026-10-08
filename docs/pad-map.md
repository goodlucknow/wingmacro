# Pad map (firmware ↔ app contract)

All app ↔ pad traffic is **raw HID** on the Vial interface (USB interface 1, 32-byte reports,
EP 0x82 in / 0x03 out). No MIDI. Verified on hardware 2026-10-07.

## Controls

Custom keycodes **WM01–WM32** (`QK_KB_0..31`, shown on Vial's "User" tab). They do nothing
locally; the pad reports them to the app. Firmware defaults:

| Control | Default |
|---|---|
| Keys (index = row × 4 + col, top-left = 0) | WM01–WM16 |
| Left / right small knob push | WM17 / WM18 |
| Left small knob CCW / CW | WM19 / WM20 |
| Right small knob CCW / CW | WM21 / WM22 |
| Big knob push | Next layer: TO(1)/TO(2)/TO(3)/TO(0) on layers 0–3 |
| Big knob turn | Mouse wheel down / up, every layer |
| Spare | WM23–WM32 |

```
┌────┬────┬────┬────┐   ┌────┐ ┌────┐
│WM01│WM02│WM03│WM04│   │WM17│ │WM18│
├────┼────┼────┼────┤   └────┘ └────┘
│WM05│WM06│WM07│WM08│
├────┼────┼────┼────┤
│WM09│WM10│WM11│WM12│      ┌───┐
├────┼────┼────┼────┤      │TO+│
│WM13│WM14│WM15│WM16│      └───┘
└────┴────┴────┴────┘
```

Every control can be remapped on the app's **Keymap** page (same raw HID commands as Vial, saved to the pad
immediately), which also edits Vial's keystroke macros, tap dance and combos. Keystroke macros need the pad
unlocked: the app runs Vial's unlock (hold key 4 + key 13). Vial itself (vial.rocks or the desktop app, with
the app stopped) is only needed for assigning `QK_BOOT`, which the app deliberately doesn't offer. Ordinary
keys (e.g. F-keys for Wing Edit) and WM keys can be mixed freely. Layers 1–3 are transparent by
default; events carry the current layer, so the app maps **(layer, WM id)** without per-layer
keycodes. What each control *does* is set entirely in the app (macros), never here.

**Reflashing resets Vial edits** (VIA's EEPROM magic is the build date). Bake anything worth
keeping into `firmware/vial/` defaults, or save a `.vil` in Vial first.

## Raw HID protocol (WM_PROTO 3)

Host → pad (reply echoes the request id, like VIA):

| Request | Meaning | Reply |
|---|---|---|
| `F0 01` | hello / keepalive: enable events for 3 s | `F0 01 <proto> <layer> <layer_state lo> <hi>` |
| `F0 02` | get state (doesn't subscribe) | same as above |
| `F0 03` | unsubscribe | — |
| `F0 04 <layer>` | switch to layer 0–3 (like `TO`); a layer event follows. Proto ≥ 2 | same as `F0 01` |
| `F0 05 <bpm×10 lo> <hi> <tenths>` | show a tempo on the OLED (e.g. 120.5 BPM) for that long, then the logo again; wakes the OLED. Proto ≥ 3 | same as `F0 01` |

Pad → host, unsolicited, **only while subscribed** (so it never blocks when nobody listens):

| Event | Bytes |
|---|---|
| WM key press/release | `F1 01 <id 1–32> <pressed> <layer> <row> <col> <seq>` |
| Layer changed | `F1 02 <layer> <seq>` |

- Knob turns report press only; row 253 = CW, 252 = CCW, col = encoder index (0 left, 1 right).
- `seq` is an 8-bit counter across all events; a gap means a dropped event → re-query with `F0 02`.
- Replies and events share the IN endpoint: route by first byte (`F1` = event).
- The app must send `F0 01` at least every 3 s (1 s recommended).
- Don't run the app and the Vial editor against the pad on the same host at the same time.

Other commands used (standard VIA/Vial): `0x11` layer count, `0x12` keymap buffer, `0x05` set key,
`FE 03` / `FE 04` get / set encoder (the get reply has no echoed header: drain pending echoes first),
`FE 05..08` unlock status/start/poll/lock, `FE 0D` tap dance / combo entries (32 + 32 on this build),
`0x0C..0x0F` macro count / buffer size / get / set (16 macros, 2655 bytes; set needs unlock), `07 41` / `07 42` VialRGB mode / direct LED HSV, `08 41` get mode.
See `tools/vialhid.py`.

## LEDs

16 per-key LEDs. LED index = key index (row × 4 + col). Knobs have no LEDs.
Firmware default: solid HSV 22/255/47 (matches the case). Brightness capped at 200.

## OLED

WING logo plus the layer number (1–4, i.e. firmware layer + 1) shown dark on a bright box, all
left-aligned because the case hides the right edge. Blanks after 30 min idle.
After a tap tempo the app shows the tempo for 2 s (`F0 05`): big digits plus a small "BPM", composed by the
firmware from glyphs generated with the logo frames (`firmware/tools/gen_oled.py`).
