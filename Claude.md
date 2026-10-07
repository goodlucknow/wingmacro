# wingmacro

Control a Behringer WING (or WING Rack) from a DOIO KB16 Rev2 macro pad, over the network via OSC, with useful LED feedback on the pad.

This is a **fresh restart**. Earlier versions (a Python/tkinter app, a Vial keymap, AutoHotkey scripts) were built in chat sessions in late 2025 and the files were lost. This document carries forward what was learned. Treat the "WING quirks" section as hard-won knowledge — verify against the WING Remote Protocols document where marked, but don't rediscover it from scratch.

---

## Goals

- Precise, tactile control of the WING from a small pad: mutes, soft (timed) mutes, mute groups, faders, sends, FX parameters, tap tempo.
- **Finest-grain control first** (e.g. 0.1 dB fader steps); speed comes from encoder acceleration, never from coarser steps.
- The console stays the source of truth — reconfiguring things on the WING itself must not require reprogramming the pad.
- Network control only (OSC over UDP). No USB/MIDI cable to the console.
- Everything lives in this repo. Nothing important exists only on one machine again.

## Where it runs

The same app must run on all three:

| Host | When | Notes |
|---|---|---|
| Surface Pro 4 (Windows 10) | When the WING travels | Also runs Wing Edit + the AHK scroll script |
| Desktop Mac | At home | Also runs Wing Edit |
| Linux container on home server | At home, desk always controllable without the Mac on | No Wing Edit here. Check USB MIDI works in the container (host kernel needs the USB audio/MIDI driver); fall back to a small VM with USB passthrough if not |

Only one host owns the pad at a time — whichever it's plugged into.

## Architecture

```
KB16 Rev2 (stock Vial firmware)
 ├─ big knob ──── mouse wheel ──→ OS ──→ Wing Edit (touch-and-turn)
 │                                 └─ Windows: AHK scroll acceleration
 ├─ keys + small knobs ── MIDI notes ──→ wingmacro app ── OSC/UDP ──→ WING
 └─ per-key RGB ←── raw HID (VialRGB direct mode) ←── wingmacro app
```

- **App**: Python, runs as a background service, cross-platform (Windows 10, macOS, Linux). Configuration through a small local web UI (replaces the old tkinter GUI, which can't run headless). Python deps are fine — the old "single standalone file" constraint was only a chat-upload workaround and no longer applies.
- **Input**: keys and the two small encoders send MIDI notes (assigned in the Vial editor). Each encoder direction is its own note; the app counts ticks and applies acceleration. Suggested libs: `mido` + `python-rtmidi`.
- **LED feedback**: app drives per-key colours via VialRGB direct mode over raw HID (`hidapi`). The app reflects WING state, e.g. red = muted, amber = soft mute fading, flash on tap tempo beats. No rainbow.
- **Big knob**: stays a standard mouse wheel on every layer. The app ignores it.

## Repo layout (proposed)

```
app/                 Python package (OSC engine, fades, tap tempo, FX db, MIDI in, LED out, web UI)
firmware/            Vial keymap for doio/kb16/rev2 (keymap.c, rules.mk, config.h, vial.json) + build/flash notes
platform/windows/    scroll-accel.ahk + autostart notes
platform/linux/      systemd unit, udev rules
docs/                pad-map.md (key/encoder → MIDI note, LED index per key), WING protocol notes
CLAUDE.md
```

`docs/pad-map.md` is the contract between firmware and app. Keep it in sync with both.

## Firmware (KB16 Rev2)

- MCU APM32F103 (STM32F103-compatible). 16 keys, 3 encoders (1 large, 2 small), per-key RGB, OLED.
- Use **vial-qmk** (separate fork from upstream QMK — don't nest it inside qmk_firmware). Keymap folder must be named `vial`.
- Lighting is **RGB_MATRIX**, not RGBLIGHT (the old rainbow-stuck bug came from using the wrong one). In `vial.json` set `"lighting": "vialrgb"`; in `rules.mk` set `VIALRGB_ENABLE = yes`. Default effect: solid/off, not rainbow.
- Previous build used 4 layers (`"layers": 4` inside the `"vial"` object of `vial.json`) and `"midi": "advanced"`.
- Big encoder → mouse wheel up/down on **every** layer.
- Bootloader: reset button on the back of the PCB, or hold key (0,0) while plugging in, or a `QK_BOOT` key.
- Check whether vial-qmk already ships a `vial` keymap for doio/kb16/rev2; if not, port from upstream QMK's `via` keymap.

## WING quirks (carry forward)

- **OSC on UDP port 2223.** The native binary protocol is on TCP 2222 — a possible alternative if OSC proves limiting, especially for FX control or live state monitoring. Discovery is by broadcast, which won't cross VLANs, so support a manually entered console IP.
- **Fader floor**: −144 dB (OSC) and −90 dB are both −∞. The last usable value above −∞ is about **−89.53 dB**. Consequences:
  - Stepping *up* from −∞ must jump straight to ~−89.5 dB, or the fader never leaves the bottom.
  - Stepping *down* past −90 dB snaps to −∞.
  - Same logic applies to sends.
- **Soft mute fades**:
  - Fade to −90 dB, not −144, then mute.
  - Never complete a fade early. A previous "early completion" shortcut made 10 s fades finish in about 6 s.
  - Fade-in: unmute and start from about −89.5 dB immediately. Don't let a slow easing curve sit inaudible for seconds.
  - Use a **perceptual curve** that spends most of the time above about −20 dB, where changes are audible. Low levels sound almost the same.
  - Must work for every fader type: ch, aux, bus, main, matrix, DCA. Use generalized OSC addressing.
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
  - The earlier build had a database of 26 FX models and about 250 parameters, transcribed from the protocol PDF. Rebuild it from the PDF into `app/` as data (JSON or YAML), not as code.
- **Tap tempo**:
  - Average the taps, and reset after a gap of 2 s or more.
  - Musical multipliers: 1/8, 1/4, 1/2, 1×, 2×.
  - Applies to all FX slots the user has selected.
  - Delay time is `/fx/X/time`. Detect delays by name: ST-DL, TAP-DL, TAPE-DL, DEL/REV.
  - **Exclude BBD-DL**. It uses `/dly` and doesn't suit tap tempo.
- ⚠️ Verify exact OSC paths for faders, mutes, sends and mute groups against the WING Remote Protocols document before relying on them. Add the PDF, or notes extracted from it, to `docs/`.

## Features (from the previous app — rebuild these)

- Per layer: 8 buttons and 4 rotaries. **Open question**: the KB16 has 16 keys and 3 encoders. How did 4 rotaries map onto it — key pairs as inc/dec, the small encoders plus layers, or something else? Settle this in `docs/pad-map.md` before building.
- Button functions:
  - hard mute
  - soft mute, with a fade time
  - mute group (1–8)
  - The config UI shows only the fields that apply to the chosen function.
- Rotary functions:
  - fader level for any fader type
  - send level (channel → bus)
  - FX parameter (slot + parameter, picked from a list of the FX currently loaded)
- A single connect/refresh action that polls state, scans the FX slots, and updates the list of delays for tap tempo.

## Open items / next priorities

1. Agree the pad map (`docs/pad-map.md`) — layers, notes, LED indices, the 4-rotary question.
2. Vial keymap: VialRGB direct mode, big knob = wheel, MIDI notes elsewhere. Flash and verify in the Vial editor.
3. App skeleton: OSC client + discovery/manual IP, MIDI in, raw HID LED out, web config UI, config file.
4. Port the WING logic above (fader floor, soft mutes, mute groups, tap tempo).
5. FX database from the protocol PDF + type-based stepping + logf scaling.
6. Encoder acceleration in the app (fine at slow speeds, faster sweeps when spun).
7. Rewrite `platform/windows/scroll-accel.ahk`. The original was lost. Consider scoping it to the Wing Edit window (`#HotIf WinActive(...)`) so other mice aren't affected.
8. Packaging/autostart for each host: Windows startup task, macOS launchd, Linux systemd.
9. Test on real hardware, against the WING at home.

## Working rules

- Commit and push often. This project has already lost its files once.
- Keep `docs/pad-map.md` and this file current when decisions change.
- Test against the real WING where possible. The dev container on the home server can reach it.
- Ask before changing goals or constraints listed here.
