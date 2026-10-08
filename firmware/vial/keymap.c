/* SPDX-License-Identifier: GPL-2.0-or-later
 * wingmacro keymap for DOIO KB16 rev2. Based on the vial-qmk vial keymap
 * by DOIO / HorrorTroll. The raw HID protocol below is the contract in
 * docs/pad-map.md.
 */

#include QMK_KEYBOARD_H
#include "raw_hid.h"

#include "oled_frames.h"

/* Custom keycodes WM01..WM32 (= QK_KB_0..31, "User" tab in Vial). They do
 * nothing locally; presses are reported to the wingmacro app over raw HID.
 *
 * Defaults:
 *   keys (row*4+col)        -> WM01..WM16
 *   left / right knob push  -> WM17 / WM18
 *   left knob CCW / CW      -> WM19 / WM20
 *   right knob CCW / CW     -> WM21 / WM22
 *   big knob push           -> next layer (TO chain 0->1->2->3->0)
 *   big knob turn           -> mouse wheel on every layer
 *   WM23..WM32              -> spare
 *
 *  ┌────┬────┬────┬────┐   ┌────┐ ┌────┐
 *  │WM01│WM02│WM03│WM04│   │WM17│ │WM18│
 *  ├────┼────┼────┼────┤   └────┘ └────┘
 *  │WM05│WM06│WM07│WM08│
 *  ├────┼────┼────┼────┤
 *  │WM09│WM10│WM11│WM12│      ┌───┐
 *  ├────┼────┼────┼────┤      │TO+│
 *  │WM13│WM14│WM15│WM16│      └───┘
 *  └────┴────┴────┴────┘
 */
enum wm_keycodes {
    WM01 = QK_KB_0, WM02, WM03, WM04, WM05, WM06, WM07, WM08,
    WM09, WM10, WM11, WM12, WM13, WM14, WM15, WM16,
    WM17, WM18, WM19, WM20, WM21, WM22,
};

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    /*  Row:    0        1        2        3        4      */
    [0] = LAYOUT(
                WM01,    WM02,    WM03,    WM04,    WM17,
                WM05,    WM06,    WM07,    WM08,    WM18,
                WM09,    WM10,    WM11,    WM12,    TO(1),
                WM13,    WM14,    WM15,    WM16
            ),
    [1] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, TO(2),
                _______, _______, _______, _______
            ),
    [2] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, TO(3),
                _______, _______, _______, _______
            ),
    [3] = LAYOUT(
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, _______,
                _______, _______, _______, _______, TO(0),
                _______, _______, _______, _______
            ),
};

#ifdef ENCODER_MAP_ENABLE
const uint16_t PROGMEM encoder_map[][NUM_ENCODERS][NUM_DIRECTIONS] = {
    [0] = { ENCODER_CCW_CW(WM19, WM20), ENCODER_CCW_CW(WM21, WM22), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [1] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [2] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
    [3] = { ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(_______, _______), ENCODER_CCW_CW(MS_WHLD, MS_WHLU) },
};
#endif

#ifdef OLED_ENABLE
    // WING logo + layer number, or briefly the tapped tempo (F0 05). Glyphs: firmware/tools/gen_oled.py.
    static uint16_t bpm_x10   = 0;
    static uint32_t bpm_until = 0;

    static uint8_t bpm_put(uint8_t *buf, uint8_t x, uint8_t g) {
        for (uint8_t c = 0; c < bpm_glyph_w[g] && x < 128; c++, x++)
            for (uint8_t page = 0; page < 4; page++)
                buf[page * 128 + x] = pgm_read_byte(&bpm_glyph_data[(bpm_glyph_col[g] + c) * 4 + page]);
        return x;
    }

    static void bpm_draw(void) {
        static uint8_t buf[512];
        memset(buf, 0, sizeof(buf));
        uint16_t whole = bpm_x10 / 10;
        uint8_t  digits[3], n = 0, x = 0;
        do { digits[n++] = whole % 10; whole /= 10; } while (whole && n < 3);
        while (n) x = bpm_put(buf, x, digits[--n]);
        if (bpm_x10 % 10) {                   /* decimal only if there is one (the app sends whole BPM) */
            x = bpm_put(buf, x, 10);          /* '.' */
            x = bpm_put(buf, x, bpm_x10 % 10);
        }
        bpm_put(buf, x + 3, 11);              /* "BPM" */
        oled_write_raw((const char *)buf, sizeof(buf));  /* only changed bytes are re-sent */
    }

    bool oled_task_user(void) {
        if (bpm_until && !timer_expired32(timer_read32(), bpm_until)) {
            bpm_draw();
        } else {
            bpm_until = 0;
            oled_write_raw_P(oled_frames[get_highest_layer(layer_state) & 3], sizeof(oled_frames[0]));
        }
        return false;
    }
#endif

/* ---- wingmacro raw HID protocol (32-byte reports, see docs/pad-map.md) ----
 * Host -> pad (reply echoes the request, VIA-style):
 *   F0 01        hello/keepalive: enable events for WM_SUBSCRIBE_MS
 *                reply: F0 01 <proto> <layer> <layer_state lo> <layer_state hi>
 *   F0 02        get state (no subscribe): same reply layout
 *   F0 03        unsubscribe
 *   F0 04 <l>    switch to layer l (like TO)
 *   F0 05 <bpm*10 lo> <hi> <tenths of a second>   show the tempo on the OLED, then the logo again (proto 3)
 * Pad -> host (unsolicited, only while subscribed):
 *   F1 01 <id> <pressed> <layer> <row> <col> <seq>   WMxx press/release
 *   F1 02 <layer> <seq>                              layer changed
 * Encoder ticks report press only (row KEYLOC_ENCODER_CW = 253, CCW = 252,
 * col = encoder index).
 */
#define WM_PROTO 3
#define WM_SUBSCRIBE_MS 3000
#define WM_CMD 0xF0
#define WM_EVT 0xF1

static uint32_t wm_sub_until = 0;
static bool     wm_subscribed = false;
static uint8_t  wm_seq = 0;

static bool wm_active(void) {
    if (wm_subscribed && timer_expired32(timer_read32(), wm_sub_until)) wm_subscribed = false;
    return wm_subscribed;
}

static void wm_send(uint8_t *msg, uint8_t len) {
    uint8_t buf[VIAL_RAW_EPSIZE] = {0};
    memcpy(buf, msg, len);
    raw_hid_send(buf, VIAL_RAW_EPSIZE);
}

static void wm_fill_state(uint8_t *data) {
    data[2] = WM_PROTO;
    data[3] = get_highest_layer(layer_state);
    data[4] = layer_state & 0xFF;
    data[5] = (layer_state >> 8) & 0xFF;
}

void raw_hid_receive_kb(uint8_t *data, uint8_t length) {
    if (data[0] != WM_CMD) {
        data[0] = id_unhandled;
        return;
    }
    switch (data[1]) {
        case 0x01:
            wm_subscribed = true;
            wm_sub_until  = timer_read32() + WM_SUBSCRIBE_MS;
            wm_fill_state(data);
            break;
        case 0x02:
            wm_fill_state(data);
            break;
        case 0x03:
            wm_subscribed = false;
            break;
        case 0x04: /* set layer (like TO): F0 04 <layer> */
            if (data[2] < 4) layer_move(data[2]);
            wm_fill_state(data);
            break;
        case 0x05: /* show tempo: F0 05 <bpm*10 lo> <hi> <tenths of a second> */
#ifdef OLED_ENABLE
            bpm_x10   = data[2] | (data[3] << 8);
            bpm_until = timer_read32() + data[4] * 100u;
            if (!bpm_until) bpm_until = 1;
            oled_on();                       /* wake it if it timed out */
#endif
            wm_fill_state(data);
            break;
        default:
            data[0] = id_unhandled;
    }
}

bool process_record_user(uint16_t keycode, keyrecord_t *record) {
    if (IS_KB_KEYCODE(keycode)) {
        bool encoder = record->event.key.row == KEYLOC_ENCODER_CW || record->event.key.row == KEYLOC_ENCODER_CCW;
        if (wm_active() && (record->event.pressed || !encoder)) {
            uint8_t msg[] = {WM_EVT, 0x01, keycode - QK_KB_0 + 1, record->event.pressed,
                             get_highest_layer(layer_state), record->event.key.row,
                             record->event.key.col, wm_seq++};
            wm_send(msg, sizeof(msg));
        }
        return false;
    }
    return true;
}

layer_state_t layer_state_set_user(layer_state_t state) {
    if (wm_active()) {
        uint8_t msg[] = {WM_EVT, 0x02, get_highest_layer(state), wm_seq++};
        wm_send(msg, sizeof(msg));
    }
    return state;
}
