# wingmacro

Control a Behringer WING (or WING Rack) from a DOIO KB16 Rev2 macro pad, over the network (WING native protocol, TCP 2222), with useful LED feedback on the pad.

This is a **fresh restart**. Earlier versions (a Python/tkinter app, a Vial keymap, AutoHotkey scripts) were built in chat sessions in late 2025 and the files were lost. This document carries forward what was learned. Treat the "WING quirks" section as hard-won knowledge — verify against the WING Remote Protocols document where marked, but don't rediscover it from scratch.

---

## Goals

- Precise, tactile control of the WING from a small pad: mutes, soft (timed) mutes, mute groups, faders, sends, FX parameters, tap tempo.
- **Finest-grain control first** (e.g. 0.1 dB fader steps); speed comes from encoder acceleration, never from coarser steps.
- The console stays the source of truth — reconfiguring things on the WING itself must not require reprogramming the pad.
- Network control only (WING native protocol over TCP). No USB/MIDI cable to the console.
- Everything lives in this repo. Nothing important exists only on one machine again.

## Where it runs

The same app must run on all three:

| Host | When | Notes |
|---|---|---|
| Surface Pro 4 (Windows 10) | When the WING travels | Also runs Wing Edit + `platform/windows/WING_TOUCH_TURN.ahk` |
| Desktop Mac | At home | Also runs Wing Edit |
| Linux container on home server | At home, desk always controllable without the Mac on | No Wing Edit here. Pad reached via USB passthrough + libusb (verified) |

**Home server host is IncusOS** — immutable, no shell, no sudo, no `/etc/udev`. Never suggest host-shell commands; host changes are only `incus config ...` run from the Mac/UI. The pad reaches the container as USB passthrough (`/dev/bus/usb/...`, d010:1601, group `claude`, rw), which follows replugs. There are no `/dev/hidraw*` nodes: reach Vial raw HID (interface 1, EP 0x82 in / 0x03 out, 32-byte reports) via **libusb** (pyusb or hidapi's libusb backend), detaching the kernel driver on interface 1 only. Bootloader `1eaf:0003` is also passed through for flashing.

Only one host owns the pad at a time — whichever it's plugged into.

## Architecture

```
KB16 Rev2 (stock Vial firmware)
 ├─ big knob ──── mouse wheel ──→ OS ──→ Wing Edit (touch-and-turn)
 │                                 └─ Windows: AHK scroll acceleration
 ├─ keys + small knobs ── raw HID events ──→ wingmacro app ── native TCP 2222 ──→ WING
 └─ per-key RGB ←── raw HID (VialRGB direct mode) ←── wingmacro app
```

- **App**: Python, runs as a background service, cross-platform (Windows 10, macOS, Linux). Configuration through a small local web UI (replaces the old tkinter GUI, which can't run headless). Python deps are fine — the old "single standalone file" constraint was only a chat-upload workaround and no longer applies.
- **Input (decided 2026-10-07: raw HID, not MIDI)**: keys and the two small encoders send custom keycodes WM01–WM32 (Vial "User" tab). The firmware reports them, with the current layer, as raw HID events on the Vial interface. LEDs and the layer query use the same channel. The protocol is in `docs/pad-map.md`. Each encoder direction is its own WM id; the app counts ticks and applies acceleration. Use `hidapi` (hidraw/IOKit/Windows), or libusb in the Linux container.
- **LED feedback**: app drives per-key colours via VialRGB direct mode over raw HID (`hidapi`). The app reflects WING state, e.g. red = muted, amber = soft mute fading, flash on tap tempo beats. No rainbow.
- **Big knob**: stays a standard mouse wheel on every layer. The app ignores it.

## Repo layout (proposed)

```
app/wingmacro/       Python package: wing.py (native client), pad.py (HID), engine.py (mappings/macros),
                     actions.py (action library), leds.py, web.py + static/, config.py
app/tests/           pytest (no hardware needed)
pyproject.toml       `pip install -e .` then `python -m wingmacro` (see app/README.md)
firmware/            Vial keymap for doio/kb16/rev2 (keymap.c, rules.mk, config.h, vial.json) + build/flash notes
platform/windows/    scroll-accel.ahk + autostart notes
platform/linux/      systemd unit, udev rules
docs/                pad-map.md (WM keycodes, raw HID protocol, LED index per key), WING protocol notes
CLAUDE.md
```

`docs/pad-map.md` is the contract between firmware and app. Keep it in sync with both.

## Firmware (KB16 Rev2)

- MCU APM32F103 (STM32F103-compatible). 16 keys, 3 encoders (1 large, 2 small), per-key RGB, OLED.
- Use **vial-qmk** (separate fork from upstream QMK — don't nest it inside qmk_firmware). Keymap folder must be named `vial`.
- Lighting is **RGB_MATRIX**, not RGBLIGHT (the old rainbow-stuck bug came from using the wrong one). In `vial.json` set `"lighting": "vialrgb"`; in `rules.mk` set `VIALRGB_ENABLE = yes`. Default effect: solid/off, not rainbow.
- 4 layers (Vial default). No MIDI.
- Big encoder → mouse wheel up/down on **every** layer.
- Small encoders: each turn direction sends its own WM keycode, and each encoder's push switch sends its own WM keycode too, with both press and release. The app handles push-and-turn, so don't use momentary layer keys on the pushes for this.
- Bootloader: reset button on the back of the PCB, or hold key (0,0) while plugging in, or a `QK_BOOT` key.
- Check whether vial-qmk already ships a `vial` keymap for doio/kb16/rev2; if not, port from upstream QMK's `via` keymap.

## WING quirks (carry forward)

- **Use the native protocol on TCP 2222, not OSC (decided 2026-10-07).** OSC (UDP 2223) allows only **one** event subscription console-wide (last requester wins), and the iPad app plus Wing Edit run alongside the pad. Native TCP gives each client its own event stream (up to 24 clients) and needs a keepalive within 10 s. WING accepts OSC-style paths in place of native hashes. Discovery: send `WING?` (UDP) to port 2222; broadcast won't cross VLANs, so also support a manually entered console IP.
- **Fader resolution**: native writes are stored as sent (−10.03 reads back −10.03; verified 2026-10-07). Still read values back.
- **Fader floor**: −144 dB and −90 dB are both −∞. **−89.5 dB** is the lowest usable value; −89.6 snaps to −∞ (verified 2026-10-07). Consequences:
  - Stepping *up* from −∞ must jump straight to ~−89.5 dB, or the fader never leaves the bottom.
  - Stepping *down* past −90 dB snaps to −∞.
  - Same logic applies to sends.
- **Fades** (was "soft mute" in the old app; now a `fade` action, followed by a separate `mute` action when wanted, decided 2026-10-07):
  - Fade to −90 dB, not −144, then snap to −∞ (muting is a separate action).
  - Never complete a fade early. A previous "early completion" shortcut made 10 s fades finish in about 6 s.
  - Fades are an app feature (WING has none). Target is a dB value, −∞, or "back" (the level before the last fade on that target).
  - Fading up from −∞: start from about −89.5 dB immediately. Don't let a slow easing curve sit inaudible for seconds.
  - Use a **perceptual curve** that spends most of the time above about −20 dB, where changes are audible. Low levels sound almost the same.
  - Must work for every fader type: ch, aux, bus, main, matrix, DCA. Use generalized path addressing.
- **Mute groups**: 8 (1–8).
- **FX**:
  - Addressing is `/fx/{slot}/{param_key}` (16 FX slots).
  - Parameter types from the protocol doc: `int`, `linf`, `logf`, `fader`, `str`.
  - Default step size by type:
    - `int` → 1
    - `linf` with a range under 10 → 0.01
    - other `linf` → 0.1
    - `fader` → 0.1 dB
  - The user can override any step.
  - `logf` (frequencies, times) needs **value-proportional stepping**. Fixed linear steps failed at the high end of the range.
  - Some parameters depend on the effect's mode and aren't always present (e.g. ST-DL offset). Handle this gracefully.
  - `str` parameters need a way to cycle through their options.
- **Tap tempo**:
  - Moving average of the tap intervals (window 4), reset after a gap of 2 s or more. Timed from key press.
  - Per key, per FX slot (a tap macro lists one or more slots). The WING has no global tempo; don't emulate one.
  - **No multipliers** (decided 2026-10-07): write the beat period; the delay's `fact` subdivision stays on the console and is mappable like any FX param.
  - Delay time is `/fx/X/time`. Any slot with a `time` param in ms qualifies (no model-name list).
  - **Exclude BBD-DL**. It uses `/dly` and doesn't suit tap tempo.
- **Native protocol facts (verified on WING Rack fw 3.1.1, 2026-10-07)**: navigate by name tokens from root (`/ch/1/fdr` → `da c1"ch" c0"1" c2"fdr"`); a data request answers `d7 <hash> <value> de`, a missing node gives a bare `de`; every client receives change events for everything without subscribing (but not for its own writes); `0xdd` on a node returns typed definitions (name, type, unit, min/max, enum items) of all its children; the console refuses a reconnect for ~1 s. Details in `app/wingmacro/wing.py`.
- **FX parameters come from the console** (`0xdd` definitions of `/fx/N`), so model/mode-dependent params are always current. No hardcoded FX database (decided 2026-10-07): new models/params from WING firmware updates work without code changes.
- Strip colours: `/ch/N/col` is 1..18; the console palette has 12 colours (13–18 look reserved for expansion; Wing Edit draws them like 12). Sampled 2026-10-07, table in `static/app.js` WCOL.
- Sends on fader (tested 2026-10-07): `/$ctl/$stat/sof` is writable (int = strip + 1; buses look like 49–64) and sets the console's SOF state, but the Rack has no fader SOF view (only the SOF frame) and **Wing Edit keeps its own SOF/selection**, so it can't be driven from the console. The only possible route to Wing Edit's SOF is its MCU/X-Touch input (Wing Edit ≥ 3.3) via a virtual MIDI port on the Wing Edit host; mapping unknown, not built.
- Input gain: `/ch/N/in/set/$g` is read-only; write `/io/in/<grp>/<n>/g` from `/ch/N/in/conn/{grp,in}`.
- Paths checked against the protocol doc (v3.1.0): `/{ch,aux,bus,main,mtx,dca}/N/fdr` and `/mute`, sends `/ch/N/send/B/lvl`, mute groups `/mgrp/1..8/mute`, FX `/fx/1..16/...`. The PDF is gitignored (free download from Behringer); see `docs/README.md`.

## Mapping model (decided 2026-10-07)

- **The pad has no fixed function layout.** In Vial the user makes some keys ordinary keys or function keys (mapped in Wing Edit for navigation), and makes others WM keys. **Every WM control is mapped in wingmacro** to whatever the user wants. Never ask "what should key X do". Build the mapping system instead.
- **Macros, in the style of DiGiCo macros.** A control triggers a user-defined macro: an ordered list of actions, with parameters, plus things like waits. Macros are data in the config, built and edited in the web UI.
- **Toggle belongs to the key (decided 2026-10-07)**: Single or Toggle behaviour. A toggle key keeps its own on/off state (deliberately not synced from the console) and runs an On list, then an Off list (automatic reverse or custom). Actions set states, never flip them. Shared macros are called from action lists with `Run macro`; no separate Macro/A-B modes.
- **Controls are identified by (layer, WM id)**, not by key position. Every event carries the current layer, so layers that pass through to the layer below still give per-layer mappings.
- **Control kinds**: a button (press and release, so it can act on press, on release or while held), and an encoder (a CCW/CW note pair, with acceleration). An encoder push can act as a modifier: turning while it is held routes to a secondary macro or function. A push with no turn can also be a button.
- **LED feedback is DiGiCo-macro style (decided 2026-10-07)**: each key has its own colour, and macros change it with an `led` action (colour, solid/flash/pulse, this or another key). Not bound to console state. The LED index is the key position (see `docs/pad-map.md`).
  - The app drives LEDs through VialRGB direct mode: the `0x07 0x41` command sets the mode, and `0x07 0x42` sets each LED's HSV. Tested on hardware 2026-10-07. In direct mode the app paints every LED, including the background colour, which is configurable and defaults to the case colour (HSV 22/255/47). The firmware caps brightness at 200.
  - Each key's LED has a background colour and state colours bound to WING state (e.g. green/red for a toggle), plus transient effects (flashing during a hold, pulsing on tap tempo).
  - The mode is set without saving to the pad's memory (`noeeprom`). On exit the app switches back to solid colour (VialRGB mode 2), and a power cycle also restores the solid colour.
- **Trigger modes per mapping** (revised 2026-10-07, see `docs/config-model.md`): one per key: `press` or `hold` (fire on release; a tap right after a hold's release cancels it) or `momentary` (on key down, restored on release, for talkback; added 2026-10-07). Originally: on press, on release, or **press-and-hold for N ms**, which acts as a safety on risky macros. While the key is held, its LED shows progress, then flashes to confirm. Releasing early cancels. The app times this from note-on and note-off.

### Action / function library (from the previous app — rebuild these as macro actions)

- Buttons: mute, fade (with time), mute group (1–8), tap tempo, connect/refresh.
- Rotaries: fader level for any fader type, send level (channel → bus), FX parameter (slot + parameter, picked from a list of the FX currently loaded).
- The config UI shows only the fields that apply to the chosen action.
- Connect/refresh polls state and scans the FX slots.
- **Parameter actions (2026-10-08)**: `param` / `param_cycle` / `param_set` reach any console parameter. The picker browses the console's own tree (`/api/params`, from `0xdd`): strip → group → parameter, plus FX slots and an "All (advanced)" tab. Readable names live in `app/wingmacro/params.py`, falling back to the console's long names, so new firmware params appear without code. Add a name there only for polish. Definitions are cached per node and dropped when that node's `mdl` changes.

## Open items / next priorities

1. ~~Pad map~~ and ~~Vial keymap~~: done (2026-10-07). See `docs/pad-map.md` and `firmware/`.
2. ~~Config model~~ (`docs/config-model.md`) and ~~app skeleton~~: done 2026-10-07, tested on the WING + pad (mute, level/floor, accel, push-turn, hold/cancel, soft-mute fades, LEDs).
3. Full mapping UI in the browser, styled after the official WING apps (no Behringer logos/names). Pad view with layer tabs → control editor (trigger, action list, LED rule) with console-fed pickers; macro library; settings. Waiting on Wing Edit screenshots from the user for the look.
   - Config is per-machine; the UI gets import/export to move configs between hosts (decided 2026-10-07).
   - Run model (decided 2026-10-07): background service + browser UI, no launchable app. Linux: systemd, UI open on the LAN (no auth for now). Windows/macOS: login autostart + tray/menu-bar icon (Open UI / Quit / status), localhost UI, PyInstaller packaging.
3b. ~~Keymap editor (Vial replacement)~~: done 2026-10-07, Keymap page; WM and ordinary keycodes, knob turns/pushes, Vial keystroke macros (with unlock), tap dance, combos. Key/encoder/tap-dance/combo writes verified on the pad; macro save + unlock still to be tried by the user. No QK_BOOT by design.
4. Test on hardware with real presses: LED feel (hold progress, armed flash), acceleration curves, tap tempo on a delay slot, gain.
7. ~~Recover the AHK script~~: the last Surface version is `platform/windows/WING_TOUCH_TURN.ahk` (AHK v2: wheel acceleration with momentum + touch-to-cursor via raw digitizer input, SP4 screen constants hard-coded). Possible improvements: scope to the Wing Edit window (`#HotIf WinActive(...)`), read the screen size at runtime.
8. Packaging/autostart for each host: Windows startup task, macOS launchd, Linux systemd.
9. Test on real hardware, against the WING at home.

## Working rules

- Commit and push often. This project has already lost its files once.
- Keep `docs/pad-map.md` and this file current when decisions change.
- Test against the real WING where possible. The dev container on the home server can reach it.
- Ask before changing goals or constraints listed here.
