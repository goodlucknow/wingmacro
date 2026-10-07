/* SPDX-License-Identifier: GPL-2.0-or-later
 * wingmacro keymap for DOIO KB16 rev2. Based on the vial-qmk vial keymap
 * by DOIO / HorrorTroll. Note numbers are the contract in docs/pad-map.md.
 */

#include QMK_KEYBOARD_H

#include "lib/layer_status/layer_status.h"

/* With MIDI defaults (channel 1, octave 2 => MI_C = note 48):
 *   keys 0..15 (row*4+col)  -> notes 48..63
 *   small knob 1 push       -> 64     small knob 2 push -> 65
 *   big knob push           -> 66
 *   small knob 1 CCW / CW   -> 67 / 68
 *   small knob 2 CCW / CW   -> 69 / 70
 *   big knob                -> mouse wheel on every layer
 *
 *  ┌───┬───┬───┬───┐   ┌───┐ ┌───┐
 *  │48 │49 │50 │51 │   │64 │ │65 │
 *  ├───┼───┼───┼───┤   └───┘ └───┘
 *  │52 │53 │54 │55 │
 *  ├───┼───┼───┼───┤
 *  │56 │57 │58 │59 │      ┌───┐
 *  ├───┼───┼───┼───┤      │66 │
 *  │60 │61 │62 │63 │      └───┘
 *  └───┴───┴───┴───┘
 */
const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    /*  Row:    0       1       2       3       4      */
    [0] = LAYOUT(
                MI_C,   MI_Cs,  MI_D,   MI_Ds,  MI_E1,
                MI_E,   MI_F,   MI_Fs,  MI_G,   MI_F1,
                MI_Gs,  MI_A,   MI_As,  MI_B,   MI_Fs1,
                MI_C1,  MI_Cs1, MI_D1,  MI_Ds1
            ),
    [1] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______
            ),
    [2] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______
            ),
    [3] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______
            ),
};

#ifdef OLED_ENABLE
    bool oled_task_user(void) {
        render_layer_status();
        return true;
    }
#endif

#ifdef ENCODER_MAP_ENABLE
const uint16_t PROGMEM encoder_map[][NUM_ENCODERS][NUM_DIRECTIONS] = {
    [0] = { ENCODER_CCW_CW(MI_G1, MI_Gs1), ENCODER_CCW_CW(MI_A1, MI_As1), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [1] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [2] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [3] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
};
#endif
