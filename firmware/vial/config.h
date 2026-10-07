/* SPDX-License-Identifier: GPL-2.0-or-later */

#pragma once

#define VIAL_KEYBOARD_UID {0x65, 0x9A, 0x6E, 0x3C, 0x47, 0x63, 0xB9, 0x9B}

#define VIAL_UNLOCK_COMBO_ROWS { 3, 0 }
#define VIAL_UNLOCK_COMBO_COLS { 0, 3 }

// Full MIDI keycode set so notes stay remappable in the Vial editor.
#define MIDI_ADVANCED

// Boot with LEDs off-ish (dim white) instead of the stock rainbow.
// The wingmacro app takes over via VialRGB direct mode.
#undef RGB_MATRIX_DEFAULT_MODE
#define RGB_MATRIX_DEFAULT_MODE RGB_MATRIX_SOLID_COLOR
#undef RGB_MATRIX_DEFAULT_HUE
#define RGB_MATRIX_DEFAULT_HUE 0
#undef RGB_MATRIX_DEFAULT_SAT
#define RGB_MATRIX_DEFAULT_SAT 0
#undef RGB_MATRIX_DEFAULT_VAL
#define RGB_MATRIX_DEFAULT_VAL 24
