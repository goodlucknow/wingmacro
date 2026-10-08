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

## Key modes (buttons)

Decided 2026-10-08 (config v5; replaces `trigger` press/hold/momentary + `toggle`). A key (or a knob's push)
has a **mode** and, unless momentary, an optional **hold to fire**.

| `mode` | Lists | Behaviour |
|---|---|---|
| `"single"` (One-shot) | `do` | Runs `do` on release, after a **cancel window** (`cancel_ms`, default `pad.cancel_ms` 400; a second tap within it cancels; 0 fires at once). Added 2026-10-08. Exception: a key whose actions include `tap` fires on key **down**, with no hold or cancel window, so taps are timed exactly. |
| `"toggle"` | `do` (On), `off` (Off) | Alternates on release (no cancel window unless hold to fire): the first fire runs On, the next Off. The key keeps its own on/off state, deliberately **not** read from the console, so "this key is on" is always definite. |
| `"momentary"` | `do` (On), `off` (Off) | On runs at key **down**, Off at key **up** (talkback). Off runs under the same key, so it takes over from an On list that is still running (e.g. a fade). If the pad disconnects mid-press, Off still runs. |

- `off` is always written by the user: there is no automatic reverse (decided 2026-10-08; guessing the inverse
  of a macro list was a recipe for surprises). Upgrading wrote any old automatic Off or momentary restore out as
  real steps.
- **Hold to fire** (`"hold": true`, `hold_ms` default 800; one-shot and toggle only) is a safety for risky
  actions. The key must be held for `hold_ms`; releasing earlier does nothing. Once the hold time is reached, the
  release **arms** the key. Then any press of the same key within `cancel_ms` (global `pad.cancel_ms`, default 400,
  overridable per key) **cancels** it, so a tap or double tap works. If nothing is pressed in that time, it fires
  (the firing is delayed by `cancel_ms`, which is accepted).
- Knob pushes offer One-shot and Toggle (no momentary or hold: the push is shared with push-and-turn).
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
- **Momentary** keys change colours back only through their Off list (e.g. a Key LED action back to the key colour).
- **Toggle keys** show their state by default: full brightness (the animation colour) while on, their own colour
  while off. `led` actions in the On/Off lists override this.
- **Press animations** (priority over the colours above; revised 2026-10-08), all in `hold_colour`, by default the
  key's own colour (else the pad background) at full brightness:
  - **Charge** on key down: the key brightens to full, over the hold time on hold-to-fire keys, over 0.2 s on others.
  - **Armed** (cancel window): a fast strobe.
  - **Fire animation** (`fire_anim`): `none` (the charge fades back), `flash` (3 flashes), or `bloom` (light swells
    out of the key into its neighbours and shrinks back, 0.8 s; `burst` is read as bloom). Hold keys default to
    flash, one-shots and toggles to none.
  - **Momentary** keys glow at full while held; with `bloom` (their default) the bloom grows and holds at its widest
    while held, shrinking back on release. `none` = just the key's glow.
- **Tap-tempo keys** flash on the beat (sharp attack, ~0.1 s decay): the tapped tempo, or else the first slot's
  `time` read from the console. With `"flash": false` on the tap action, the key flashes only for the 8 beats after
  the last tap (not counting the tap itself), then rests.
- The `led` action's `pulse` effect breathes at about 0.5 Hz.
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
| `fade` | `target`, `db` (number, `"-inf"` or `"back"`), `rel?`, `time` (s), `wait` (default true) | button | Timed fader/send move, an app feature (the WING has none). Perceptual curve; up from −∞ starts at −89.5 dB at once; to −∞ fades to −90 dB then snaps; never finishes early. `back` returns to the level before the last fade or set on that target; `rel` fades by a change (as `level_set`). With `wait`, the next action waits for the fade. Muting is a separate `mute` action. (Replaces the old `softmute`; configs are converted.) |
| `mgrp` | `n` 1–8, `op: on\|off` | button | |
| `macro` | `name` | button | Runs a shared macro's actions inline. |
| `level` | `target`, `step` (dB, default 0.1) | rotary | Stepping up from −∞ jumps to −89.53 dB. Stepping down past −90 dB snaps to −∞. Reads the value back. |
| `gain` | `target` (`ch/N`), `step` (dB, default 0.5) | rotary | Input gain of the channel's source (`/ch/N/in/set/$g` → `/io/in/...`). The path needs checking on hardware. |
| `level_set` | `target`, `db` (number, `"-inf"` or `"back"`), `rel?` | button | With `rel`, `db` is a change (+6 / −6): −∞ stays −∞, capped at +10, below −89.5 is −∞. `"back"` = the level before the last set or fade on this target (exact even if a boost hit the cap), e.g. a momentary boost: On +6 `rel`, Off Back. Cancels a running fade on the target. |
| `param` | `path`, `step?`, `wrap?`, `plabel?`, `pref?`, `label?`, `screen?` | rotary | Any console parameter (e.g. `/ch/3/send/MX1/lvl`, `/fx/3/time`), stepped by its console type: int 1, linf 0.01 (range < 10) or 0.1 but at least one console step (the WING stores linf on a grid of `steps` values, e.g. 1 % for FX feed, 0.5 dB for dyn threshold), fader 0.1 dB with the floor rules, logf proportional to the value, option lists one option per tick. Stops at the ends unless `wrap` (option lists and ints wrap round). `plabel` is the display name saved by the picker. |

**FX model changes** (`resolve.py`): param steps on a node with a model (FX slots, inserts) carry `pref` = `{path, model, key, longname, unit, type, idx}`, stamped by the app on save and on connect (not by the UI; kept when a UI copy lacks it). When the current model lacks the key, the step drives the equivalent: same key → alias role (feed/rep/fb/sust, time/dly, mspd/mod, …) → same long name and unit → same param number `idx` (what the WING does itself) → nothing (no write, pad screen shows "n/a"). Never across number/option-list kinds. A different param type drops the step's `step` and `label`. A `value` set only lands on an equivalent of the same type and unit. The UI shows "now: <param> (made on <model>)" or "not in <model>" (`/api/resolve`). Model defs of fw 3.1.1: `docs/wing-fx-models-3.1.1.json`.

Rotary actions (`level`, `gain`, `param`, and `param_set` Increase/Decrease) show the new value on the pad's OLED for 1.5 s (`F0 06`): a small label (`label`, else automatic, e.g. "FX3 Pre delay", "CH1 S2 Level") over the value formatted by its unit ("25.0 ms", "1.25 s", "12.5 kHz", "-∞ dB", option names as the console gives them). `"screen": false` turns it off for that step.
| `param_set` | `path`, `value` or `op: inc\|dec`, `step?`, `wrap?`, `plabel?`, `pref?` | button | Sets any parameter to a value (coerced to its type), or one step up/down: the next/previous option for lists. Stops at the ends unless `wrap`. |
| `tap` | `slots` (list), `window?` (default 4), `flash?` (default true) | button | Tap time is taken at the key press. Moving average of the last `window` intervals; a gap of 2 s or more starts over. Rounded to a whole BPM. Writes the beat period as-is to `/fx/N/time` of each listed slot. No multiplier: the delay's own `fact` (subdivision) stays on the console and can be mapped like any param. Slots without a `time` param in ms (e.g. BBD-DL) are skipped. Tap state is per slot set; the WING has no global tempo. |
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
  "version": 5,
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
        "1":  { "mode": "toggle", "do": [{ "do": "mute", "target": "ch/1", "op": "on" }],
                "off": [{ "do": "mute", "target": "ch/1", "op": "off" }] },
        "2":  { "mode": "single", "do": [
                  { "do": "fade", "target": "main/1", "db": "-inf", "time": 5 },
                  { "do": "mute", "target": "main/1", "op": "on" } ] },
        "4":  { "mode": "toggle", "hold": true, "hold_ms": 800, "background": [0, 255, 40],
                "fire_anim": "bloom", "hold_colour": "red",
                "do":  [{ "do": "macro", "name": "Band out" }, { "do": "led", "colour": "red" }],
                "off": [{ "do": "mgrp", "n": 2, "op": "off" }, { "do": "mute", "target": "dca/1", "op": "off" },
                        { "do": "fade", "target": "dca/1", "db": 0, "time": 10 }, { "do": "led", "colour": "base" }] },
        "6":  { "mode": "momentary", "name": "Talkback", "do": [{ "do": "mute", "target": "ch/40", "op": "off" }],
                "off": [{ "do": "mute", "target": "ch/40", "op": "on" }] },
        "13": { "mode": "single", "do": [{ "do": "tap", "slots": [3, 4] }] },
        "16": { "mode": "single", "do": [{ "do": "refresh" }] }
      },
      "encoders": {
        "left":  { "turn": [{ "do": "level", "target": "main/1" }],
                   "push_turn": [{ "do": "level", "target": "ch/1/send/3" }],
                   "push": { "do": [{ "do": "level_set", "target": "main/1", "db": 0 }] } },
        "right": { "turn": [{ "do": "param", "path": "/fx/3/time" }], "accel": "normal" }
      }
    },
    "1": {
      "buttons": { "1": { "mode": "toggle", "do": [{ "do": "mute", "target": "ch/9", "op": "on" }],
                         "off": [{ "do": "mute", "target": "ch/9", "op": "off" }] } }
    }
  }
}
```

Layer 1 here overrides only WM01. Everything else falls back to layer 0.

## Open questions

None. Defaults are to be tuned in practice.
