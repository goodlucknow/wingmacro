# Pad map (firmware ↔ app contract)

All MIDI on **channel 1**, velocity 127. Keys send note-on when pressed and note-off when released.

## Notes

| Control | Note |
|---|---|
| Keys 0–15 (index = row × 4 + col, top-left = 0) | 48–63 |
| Small knob 1 push (top-left knob) | 64 |
| Small knob 2 push (top-right knob) | 65 |
| Big knob push | 66 (app may ignore) |
| Small knob 1 CCW / CW | 67 / 68 (each tick sends a quick on/off) |
| Small knob 2 CCW / CW | 69 / 70 |
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

## LEDs

16 per-key LEDs, VialRGB direct mode. LED index = key index (row × 4 + col).

## Layers

Firmware layer 0 holds everything; layers 1–3 are transparent (big knob stays wheel).

## Open

- Paging: proposed that "layers" are app-side pages (firmware notes never change), so the
  LEDs and the web UI always know which page is active.
- Use of the 8 keys beyond the per-page buttons (page select, tap tempo, connect/refresh, spare).
- Push without turn: optional button action per page?
- Verify encoder directions and which small knob is "1" on hardware.
