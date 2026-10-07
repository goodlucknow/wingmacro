# Pad map (firmware ↔ app contract)

All MIDI on **channel 1**, velocity 127; note-off is a real `0x80` message.
Verified on hardware 2026-10-07 (keys, knob pushes, knob directions; big knob sends no MIDI). Keys send note-on when pressed and note-off when released.

## Notes

| Control | Note |
|---|---|
| Keys 0–15 (index = row × 4 + col, top-left = 0) | 48–63 |
| Left small knob push | 64 |
| Right small knob push | 65 |
| Big knob push | 66 (app may ignore) |
| Left small knob CCW / CW | 67 / 68 (each tick sends a quick on/off) |
| Right small knob CCW / CW | 69 / 70 |
| Big knob turn | Mouse wheel down / up, every layer |

```
┌───┬───┬───┬───┐   ┌───┐ ┌───┐
│48 │49 │50 │51 │   │64 │ │65 │
├───┼───┼───┼───┤   └───┘ └───┘
│52 │53 │54 │55 │
├───┼───┼───┼───┤
│56 │57 │58 │59 │      ┌───┐
├───┼───┼───┼───┤      │66 │
│60 │61 │62 │63 │      └───┘
└───┴───┴───┴───┘
```

These are only the **defaults**. Every key, knob push and knob direction can be remapped in Vial
(vial.rocks in Chrome, or the Vial desktop app) — ordinary keys and MIDI notes can be mixed
freely. The app therefore keys its config **by MIDI note, not by key position**; a key remapped
to an ordinary keycode is simply invisible to the app.

## LEDs

16 per-key LEDs, VialRGB direct mode. LED index = key index (row × 4 + col).

## Layers

Firmware layer 0 holds everything; layers 1–3 are transparent (big knob stays wheel).
Currently set in Vial: big knob push = TO(1)/TO(2)/TO(3)/TO(0) on layers 0–3 (so note 66 is
not sent). Read the live keymap with `tools/vialhid.py dump`.

## Open

- Paging: proposed that "layers" are app-side pages (firmware notes never change), so the
  LEDs and the web UI always know which page is active.
- Use of the 8 keys beyond the per-page buttons (page select, tap tempo, connect/refresh, spare).
- Push without turn: optional button action per page?
