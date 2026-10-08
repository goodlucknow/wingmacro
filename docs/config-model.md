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

A key has **one** trigger: `press` or `hold` (both **fire on release**), or `momentary` (acts on key **down**).

| Trigger | Behaviour |
|---|---|
| `"press"` | Fires on release. |
| `"hold"`, `hold_ms` (default 800) | Must be held for `hold_ms`; releasing earlier does nothing. Once the hold time is reached, the release **arms** the key. Then any press of the same key within `cancel_ms` (global `pad.cancel_ms`, default 400, settable in the web UI; can be overridden per key) **cancels** it, so a tap or double tap works. If nothing is pressed in that time, it fires. The firing is delayed by `cancel_ms`, which is accepted. |

| `"momentary"` | Runs on key down and stays active while held (talkback). On release the macro is stopped, every parameter it wrote is restored to its value from before the press, and fades go back to where they started. A `toggle` uses its A side. |

**Behaviour** (decided 2026-10-07; replaces the old Actions / Macro / Toggle A/B modes):
- **Single**: `do` is the list of actions run on each fire.
- **Toggle** (`"toggle": true`): the key keeps its own on/off state, deliberately **not** read from the console,
  so "this key is on" is always definite. The first press runs `do` (On), the next runs Off, and so on.
  - Off is `"off": [...]`, always written by hand (decided 2026-10-08: no automatic reverse; guessing the
    inverse of a macro list was a recipe for surprises). Config v4 wrote any old automatic Off out as real steps.
- Momentary keys are always Single: their release restores everything.
- Actions **set** a state (`op: on|off`, fade to a level); they never flip it. `op: toggle` is still accepted for
  old configs.
- Shared **macros** (Macros page) are reusable action lists. A list runs one with `{"do": "macro", "name": "..."}`
  (inline, nesting allowed up to 8 deep).
- Configs from before this change (`"version": 1`) are converted on load, and the old file is kept as `.json.bak`.

LED feedback for `hold`:
- While held: the key fills from the background colour to the target colour.
- Armed: fast flash for the length of `cancel_ms`.
- Fired: 3 flashes, then back to the state colour.
- Cancelled, or released too early: snaps back to the state colour.

## LED rules (DiGiCo-macro style, decided 2026-10-07)

- LEDs are **not** bound to console state. Each key shows its own colour, and macros change it with the `led` action.
- **Key colour**: `background` on the mapping (HSV or palette name). The default is `pad.background`, HSV `[22,255,47]` (case colour).
  Unmapped and non-WM keys show the pad background.
- **`led` action**: `colour` (palette name, HSV, or `"base"` to go back to the key colour), `effect` (`solid` | `flash` | `pulse`),
  and optional `layer` + `key` (1-based) to address another key. The default target is the key that ran the macro.
  Example: a toggle whose A side sets green and B side sets red.
- The colour state belongs to (mapping layer, key), so a key inherited on other layers shows the same colour. State is kept in memory: after an app restart, keys show their own colour and toggles start on A.
- **Momentary** keys restore any colours they changed when released.
- **Animations** (priority over the colour above): the hold glow while held and the armed flash, plus a **fire animation** when the key fires.
  Set it with `fire_anim`: `none`, `flash`, or `burst` (a flash plus a ring of light spreading out across the pad). Hold keys default to `flash`, all others to `none`.
  Animations use `hold_colour` (default white). The tap-tempo beat flash runs on tap keys.
- Brightness is the V of an HSV colour (0–200). In the UI, every colour picker has a brightness slider, so a palette colour can be stored at any brightness.
- Colours are HSV triples (0–255, as in VialRGB) or palette names: the WING's 12 colours in its order (`steel`, `sky`, `indigo`, `teal`, `green`, `olive`, `yellow`, `orange`, `red`, `coral`, `magenta`, `purple`), plus `white` and `off`, with LED values tuned for the pad (orange = the case/UI amber). The older names `crimson`, `amber`, `cyan` and `blue` are still accepted. The firmware caps brightness at 200.
- When the layer changes, the app repaints all 16 LEDs with that layer's colours. On exit it restores VialRGB mode 2.

## Targets

Fader-type targets are strings: `ch/N`, `aux/N`, `bus/N`, `main/N`, `mtx/N`, `dca/N`.
Sends are `ch/N/send/B`. The app maps a target to `/fdr` + `/mute` paths, or `/lvl` + `/on` for sends.
Every fader-type target follows the same floor rules.

## Action library

| Action | Params | Kind | Notes |
|---|---|---|---|
| `mute` | `target`, `op: on\|off` | button | |
| `fade` | `target`, `db` (number, `"-inf"` or `"back"`), `time` (s), `wait` (default true) | button | Timed fader/send move, an app feature (the WING has none). Perceptual curve; up from −∞ starts at −89.5 dB at once; to −∞ fades to −90 dB then snaps; never finishes early. `back` returns to the level before the last fade on that target. With `wait`, the next action waits for the fade. Muting is a separate `mute` action. (Replaces the old `softmute`; configs are converted.) |
| `mgrp` | `n` 1–8, `op: on\|off` | button | |
| `macro` | `name` | button | Runs a shared macro's actions inline. |
| `level` | `target`, `step` (dB, default 0.1) | rotary | Stepping up from −∞ jumps to −89.53 dB. Stepping down past −90 dB snaps to −∞. Reads the value back. |
| `gain` | `target` (`ch/N`), `step` (dB, default 0.5) | rotary | Input gain of the channel's source (`/ch/N/in/set/$g` → `/io/in/...`). The path needs checking on hardware. |
| `level_set` | `target`, `db` (number or `"-inf"`) | button | |
| `fx` | `slot`, `param`, `step?` | rotary | The default step depends on the type (int 1, linf 0.01/0.1, fader 0.1 dB). logf steps are proportional to the value, about 1% by default. Skipped silently if the parameter isn't present in the current mode. |
| `fx_cycle` | `slot`, `param`, `dir: next\|prev` | button | For `str` params. Can also be used as a rotary. |
| `fx_set` | `slot`, `param`, `value` | button | |
| `param` | `path`, `step?`, `plabel?` | rotary | Any console parameter (e.g. `/ch/3/send/MX1/lvl`). Steps by its console type, same rules as `fx`. `plabel` is the display name saved by the picker. |
| `param_cycle` | `path`, `dir: next\|prev`, `plabel?` | button/rotary | Cycles an enum (or small int) parameter. |
| `param_set` | `path`, `value`, `plabel?` | button | Sets any parameter, coerced to its console type. |
| `tap` | `slots` (list), `window?` (default 4) | button | Tap time is taken at the key press. Moving average of the last `window` intervals; a gap of 2 s or more starts over. Writes the beat period as-is to `/fx/N/time` of each listed slot. No multiplier: the delay's own `fact` (subdivision) stays on the console and can be mapped like any param. Slots without a `time` param in ms (e.g. BBD-DL) are skipped. Tap state is per slot set; the WING has no global tempo. |
| `refresh` | — | button | Reconnects if needed, polls state and rescans the FX slots (and so the delays). |
| `led` | `colour`, `effect?`, `layer?` + `key?` | button | Sets a key's LED (see LED rules). |
| `wait` | `ms` | step | |
| `set` | `path`, `value` | button | Advanced: writes any WING parameter by path, for things the library doesn't cover yet. |

Rotary acceleration is set per encoder mapping as `accel: off | fine | normal` (presets, default `fine`).
At slow speeds each tick is exactly one step. Faster turning multiplies the *number* of steps; the step size never changes.

## File format

**JSON** (decided), in the per-OS config directory (`wingmacro.json`), written atomically with a `.bak` copy.

```json
{
  "version": 4,
  "console": { "ip": "192.168.1.62", "discover": true },
  "pad": { "background": [22, 255, 47], "cancel_ms": 400, "hold_ms": 800 },
  "macros": {
    "Band out": { "steps": [
      { "do": "fade", "target": "dca/1", "db": "-inf", "time": 10 },
      { "do": "mute", "target": "dca/1", "op": "on" },
      { "do": "mgrp", "n": 2, "op": "on" }
    ] }
  },
  "layers": {
    "0": {
      "buttons": {
        "1":  { "trigger": "press", "toggle": true, "do": [{ "do": "mute", "target": "ch/1", "op": "on" }] },
        "2":  { "trigger": "press", "toggle": true, "do": [
                  { "do": "fade", "target": "main/1", "db": "-inf", "time": 5 },
                  { "do": "mute", "target": "main/1", "op": "on" },
                  { "do": "led", "colour": "red" } ] },
        "4":  { "trigger": "hold", "hold_ms": 800, "toggle": true, "background": [0, 255, 40],
                "fire_anim": "burst", "hold_colour": "red",
                "do":  [{ "do": "macro", "name": "Band out" }, { "do": "led", "colour": "red" }],
                "off": [{ "do": "mgrp", "n": 2, "op": "off" }, { "do": "mute", "target": "dca/1", "op": "off" },
                        { "do": "fade", "target": "dca/1", "db": 0, "time": 10 }, { "do": "led", "colour": "base" }] },
        "6":  { "trigger": "momentary", "name": "Talkback", "do": [{ "do": "mute", "target": "ch/40", "op": "off" }] },
        "13": { "trigger": "press", "do": [{ "do": "tap", "slots": [3, 4] }] },
        "16": { "trigger": "press", "do": [{ "do": "refresh" }] }
      },
      "encoders": {
        "left":  { "turn": [{ "do": "level", "target": "main/1" }],
                   "push_turn": [{ "do": "level", "target": "ch/1/send/3" }],
                   "push": { "do": [{ "do": "level_set", "target": "main/1", "db": 0 }] } },
        "right": { "turn": [{ "do": "fx", "slot": 3, "param": "time" }], "accel": "normal" }
      }
    },
    "1": {
      "buttons": { "1": { "trigger": "press", "toggle": true, "do": [{ "do": "mute", "target": "ch/9", "op": "on" }] } }
    }
  }
}
```

Layer 1 here overrides only WM01. Everything else falls back to layer 0.

## Open questions

None. Defaults are to be tuned in practice.
