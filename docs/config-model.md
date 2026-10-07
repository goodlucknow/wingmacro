# Config model (draft for review)

How wingmacro maps pad controls to WING actions. The app reads one config file and the web UI edits it.
Firmware details are in `pad-map.md`. This file defines what the app does with the events it receives.

## Controls

- A control is identified by **(layer, WM id)**: layer 0–3, WM id 1–32. Key position doesn't matter for lookup.
- **Button**: any WM id that sends press and release. Keys and knob pushes are buttons.
- **Encoder**: a group of WM ids `{ccw, cw, push?}`, declared once in `encoders`. The defaults are
  `left = {ccw: 19, cw: 20, push: 17}` and `right = {ccw: 21, cw: 22, push: 18}`. If the user remaps
  WM ids in Vial, they edit this group.
- **Push as modifier**: an encoder mapping has `turn`, plus optional `push_turn` (used while the push is
  held) and `push` (a button mapping). `push` fires on release only if no turn happened during the hold.
- **Layer fallback**: if (layer, id) has no mapping, the app tries lower layers, down to layer 0.
  So layer 0 holds the common mappings and higher layers override only what they change.
- **LED index**: comes from the pad's keymap (`0x12`), read at connect, plus row/col from events.
  A mapping never has to state its LED, but `led_index` can override it.

## Macros

- A macro is a named, ordered list of **steps**. Each step is an action with its parameters, see the library below.
- Mappings refer to macros by name, or define a list of steps inline.
- Steps run in order. `wait` steps don't block other controls: each macro run is its own async task.
- If a macro is triggered again while it's still running, the default is to **restart** it.
  `"retrigger": "ignore" | "restart" | "parallel"` changes this.
- **Encoder turns** bind to *rotary* actions only, with no waits. Every rotary step in the list gets the same
  accelerated tick count, so one knob can move several faders together.

## Trigger modes (buttons)

A button mapping has any of the following:

| Key | Fires |
|---|---|
| `press` | on press |
| `release` | on release (`press` + `release` together = momentary, e.g. talkback-style mute while held) |
| `hold: {ms, do}` | after the key has been held for `ms`. Releasing earlier cancels. |

While a `hold` is pending, the key's LED fills from the background colour to the target colour over `ms`.
When it fires, the LED flashes 3× and then returns to its state colour. Releasing early snaps the LED back.
The app times the hold from the press and release events.

## LED rules

- **Background**: `pad.background`, HSV, default `[22,255,47]` (case colour). Every unbound key shows it,
  including non-WM keys. Per-layer and per-key overrides are allowed.
- **State colour**: `led: {bind, on, off}`, where `bind` is a WING state expression:
  - `mute:<target>`
  - `mgrp:<n>`
  - `softmute:<target>`: on while faded down, `fading` while a fade is running
  - `floor:<target>`: on at −∞
  - `fx:<slot>/<param>==<value>`
  - `connected`
- `led: "auto"` (the default) derives the binding from the first action in the macro:
  - mute → red when on / background when off
  - softmute → red when down, pulsing amber while fading
  - mgrp → red when on
  - tap → pulses on the beat
- **Transient effects** layer on top in this priority: hold progress / confirm flash > `flash` (press feedback) >
  tap pulse > state colour > background.
- Colours are HSV triples (0–255, as in VialRGB) or palette names (`red`, `green`, `amber`, `blue`, `white`, `off`).
  The firmware caps brightness at 200.
- When the layer changes, the app repaints all 16 LEDs with that layer's rules. On exit it restores VialRGB mode 2.

## Targets

Fader-type targets are strings: `ch/N`, `aux/N`, `bus/N`, `main/N`, `mtx/N`, `dca/N`.
Sends are `ch/N/send/B`. The app maps a target to `/fdr` + `/mute` paths, or `/lvl` + `/on` for sends.
Every fader-type target follows the same floor rules.

## Action library

| Action | Params | Kind | Notes |
|---|---|---|---|
| `mute` | `target`, `op: toggle\|on\|off` | button | |
| `softmute` | `target`, `op: toggle\|down\|up`, `time` (s), `curve: perceptual` | button | Fades down to −90 dB and then mutes. Fading up unmutes, starts at −89.5 dB and returns to the stored level. Never finishes early. A new fade on the same target takes over from the current level. |
| `mgrp` | `n` 1–8, `op` | button | |
| `level` | `target`, `step` (dB, default 0.1) | rotary | Stepping up from −∞ jumps to −89.53 dB. Stepping down past −90 dB snaps to −∞. Reads the value back. |
| `level_set` | `target`, `db` (number or `"-inf"`) | button | |
| `fx` | `slot`, `param`, `step?` | rotary | The default step depends on the type (int 1, linf 0.01/0.1, fader 0.1 dB). logf steps are proportional to the value, about 1% by default. Skipped silently if the parameter isn't present in the current mode. |
| `fx_cycle` | `slot`, `param`, `dir: next\|prev` | button | For `str` params. Can also be used as a rotary. |
| `fx_set` | `slot`, `param`, `value` | button | |
| `tap` | — | button | Averages the taps and resets after a gap of 2 s or more. Writes `/fx/X/time` to every slot in `tap_tempo.slots`, each with its own multiplier. |
| `refresh` | — | button | Reconnects if needed, polls state and rescans the FX slots (and so the delays). |
| `wait` | `ms` | step | |
| `set` | `path`, `value` | button | Raw native/OSC-path escape hatch. |

Rotary acceleration is set per encoder mapping as `accel: off | fine | normal` (presets, default `fine`).
At slow speeds each tick is exactly one step. Faster turning multiplies the *number* of steps; the step size never changes.

## File format

**JSON**, in the per-OS config directory (`wingmacro.json`), written atomically with a `.bak` copy.
I chose JSON over YAML because the web UI rewrites the file (YAML comments wouldn't survive), and JSON
needs no extra dependency.

```json
{
  "version": 1,
  "console": { "ip": "192.168.1.62", "discover": true },
  "pad": { "background": [22, 255, 47] },
  "encoders": {
    "left":  { "ccw": 19, "cw": 20, "push": 17 },
    "right": { "ccw": 21, "cw": 22, "push": 18 }
  },
  "tap_tempo": { "slots": { "3": 1, "4": 0.5 } },
  "macros": {
    "band_out": {
      "retrigger": "ignore",
      "steps": [
        { "do": "softmute", "target": "dca/1", "op": "down", "time": 10 },
        { "do": "wait", "ms": 2000 },
        { "do": "mgrp", "n": 2, "op": "on" }
      ]
    }
  },
  "layers": {
    "0": {
      "buttons": {
        "1":  { "press": [{ "do": "mute", "target": "ch/1", "op": "toggle" }] },
        "2":  { "press": [{ "do": "softmute", "target": "main/1", "op": "toggle", "time": 5 }] },
        "4":  { "hold": { "ms": 800, "do": "band_out" }, "led": { "bind": "softmute:dca/1", "on": "red", "off": "green" } },
        "13": { "press": [{ "do": "tap" }] },
        "16": { "press": [{ "do": "refresh" }], "led": { "bind": "connected", "on": "off", "off": "red" } }
      },
      "encoders": {
        "left":  { "turn": [{ "do": "level", "target": "main/1" }],
                   "push_turn": [{ "do": "level", "target": "ch/1/send/3" }],
                   "push": { "press": [{ "do": "level_set", "target": "main/1", "db": 0 }] } },
        "right": { "turn": [{ "do": "fx", "slot": 3, "param": "time" }], "accel": "normal" }
      }
    },
    "1": {
      "buttons": { "1": { "press": [{ "do": "mute", "target": "ch/9", "op": "toggle" }] } }
    }
  }
}
```

Layer 1 here overrides only WM01. Everything else falls back to layer 0.

## Open questions

1. Should layer fallback be on (as drafted), or should each layer be fully independent?
2. Tap vs long-press on the same key (`press` short + `hold` long), or keep `hold` exclusive as drafted?
3. Should tap-tempo multipliers be per slot (as drafted) or one global multiplier?
4. JSON is OK? (YAML would only be worth it if you plan to hand-edit with comments.)
5. Should soft-mute "stored level" survive an app restart (persisted to a state file), or be re-read from the console?
6. Is a raw `set` action OK as an escape hatch for paths the library doesn't cover yet?
