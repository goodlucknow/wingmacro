# Config model (draft for review)

How wingmacro maps pad controls to WING actions. The app reads one config file and the web UI edits it.
Firmware details are in `pad-map.md`. This file defines what the app does with the events it receives.

## Controls

- A control is identified by **(layer, WM id)**: layer 0–3, WM id 1–32. Key position doesn't matter for lookup.
- **Button**: any WM id that sends press and release. Keys and knob pushes are buttons.
- **Encoder**: `left` or `right`, identified from the event's position, not its WM id. Turns report
  row 253/252 (CW/CCW) with col = knob index. Pushes are keys (0,4) and (1,4). Any WM id on a knob works,
  and nothing has to be declared in the config.
- **Push as modifier**: an encoder mapping has `turn`, plus optional `push_turn` (used while the push is
  held) and `push` (a button mapping). `push` fires on release only if no turn happened during the hold.
- **Layer fallback** (decided): if (layer, id) has no mapping, the app tries lower layers, down to layer 0.
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

A key has **one** trigger, `press` or `hold`. Both **fire on release**.

| Trigger | Behaviour |
|---|---|
| `"press"` | Fires on release. |
| `"hold"`, `hold_ms` (default 800) | Must be held for `hold_ms`; releasing earlier does nothing. Once the hold time is reached, the release **arms** the key. Then any press of the same key within `cancel_ms` (global `pad.cancel_ms`, default 400, settable in the web UI; can be overridden per key) **cancels** it, so a tap or double tap works. If nothing is pressed in that time, it fires. The firing is delayed by `cancel_ms`, which is accepted. |

Each key has one of two kinds of action, set by `do`:
- `"do": <macro>` fires the same macro every time.
- `"do": {"toggle": [<macro A>, <macro B>]}` alternates between A and B. The app keeps the A/B state and the LED shows it.
  Actions that already toggle (e.g. `mute op: toggle`) don't need this.

LED feedback for `hold`:
- While held: the key fills from the background colour to the target colour.
- Armed: fast flash for the length of `cancel_ms`.
- Fired: 3 flashes, then back to the state colour.
- Cancelled, or released too early: snaps back to the state colour.

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
  - tap → pulses on that key's own tempo
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
| `softmute` | `target`, `op: toggle\|down\|up`, `time` (s) | button | An app feature; the WING has no soft mute. **Down**: perceptual fade to −90 dB, then mute. **Up**: unmute, start at −89.5 dB, perceptual fade to **0 dB**. No stored return level. Never finishes early. A new fade on the same target takes over from the current level. |
| `mgrp` | `n` 1–8, `op` | button | |
| `level` | `target`, `step` (dB, default 0.1) | rotary | Stepping up from −∞ jumps to −89.53 dB. Stepping down past −90 dB snaps to −∞. Reads the value back. |
| `gain` | `target` (`ch/N`), `step` (dB, default 0.5) | rotary | Input gain of the channel's source (`/ch/N/in/set/$g` → `/io/in/...`). The path needs checking on hardware. |
| `level_set` | `target`, `db` (number or `"-inf"`) | button | |
| `fx` | `slot`, `param`, `step?` | rotary | The default step depends on the type (int 1, linf 0.01/0.1, fader 0.1 dB). logf steps are proportional to the value, about 1% by default. Skipped silently if the parameter isn't present in the current mode. |
| `fx_cycle` | `slot`, `param`, `dir: next\|prev` | button | For `str` params. Can also be used as a rotary. |
| `fx_set` | `slot`, `param`, `value` | button | |
| `tap` | `slots` (list), `window?` (default 4) | button | Tap time is taken at the key press. Moving average of the last `window` intervals; a gap of 2 s or more starts over. Writes the beat period as-is to `/fx/N/time` of each listed slot. No multiplier: the delay's own `fact` (subdivision) stays on the console and can be mapped like any param. Slots without a `time` param in ms (e.g. BBD-DL) are skipped. Tap state is per slot set; the WING has no global tempo. |
| `refresh` | — | button | Reconnects if needed, polls state and rescans the FX slots (and so the delays). |
| `wait` | `ms` | step | |
| `set` | `path`, `value` | button | Advanced: writes any WING parameter by path, for things the library doesn't cover yet. |

Rotary acceleration is set per encoder mapping as `accel: off | fine | normal` (presets, default `fine`).
At slow speeds each tick is exactly one step. Faster turning multiplies the *number* of steps; the step size never changes.

## File format

**JSON** (decided), in the per-OS config directory (`wingmacro.json`), written atomically with a `.bak` copy.

```json
{
  "version": 1,
  "console": { "ip": "192.168.1.62", "discover": true },
  "pad": { "background": [22, 255, 47], "cancel_ms": 400 },
  "macros": {
    "band_out": {
      "retrigger": "ignore",
      "steps": [
        { "do": "softmute", "target": "dca/1", "op": "down", "time": 10 },
        { "do": "wait", "ms": 2000 },
        { "do": "mgrp", "n": 2, "op": "on" }
      ]
    },
    "band_in": { "steps": [
        { "do": "mgrp", "n": 2, "op": "off" },
        { "do": "softmute", "target": "dca/1", "op": "up", "time": 10 }
    ] }
  },
  "layers": {
    "0": {
      "buttons": {
        "1":  { "trigger": "press", "do": [{ "do": "mute", "target": "ch/1", "op": "toggle" }] },
        "2":  { "trigger": "press", "do": [{ "do": "softmute", "target": "main/1", "op": "toggle", "time": 5 }] },
        "4":  { "trigger": "hold", "hold_ms": 800, "do": { "toggle": ["band_out", "band_in"] },
                "led": { "bind": "softmute:dca/1", "on": "red", "off": "green" } },
        "13": { "trigger": "press", "do": [{ "do": "tap", "slots": [3, 4] }] },
        "16": { "trigger": "press", "do": [{ "do": "refresh" }], "led": { "bind": "connected", "on": "off", "off": "red" } }
      },
      "encoders": {
        "left":  { "turn": [{ "do": "level", "target": "main/1" }],
                   "push_turn": [{ "do": "level", "target": "ch/1/send/3" }],
                   "push": { "trigger": "press", "do": [{ "do": "level_set", "target": "main/1", "db": 0 }] } },
        "right": { "turn": [{ "do": "fx", "slot": 3, "param": "time" }], "accel": "normal" }
      }
    },
    "1": {
      "buttons": { "1": { "trigger": "press", "do": [{ "do": "mute", "target": "ch/9", "op": "toggle" }] } }
    }
  }
}
```

Layer 1 here overrides only WM01. Everything else falls back to layer 0.

## Open questions

None. Defaults are to be tuned in practice.
