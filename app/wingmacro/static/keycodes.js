"use strict";
// QMK/Vial keycodes (values from vial-qmk quantum/keycodes.h) with short display names.
const KC = (() => {
  const basic = {};
  const set = (v, n) => { basic[v] = n; };
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach((c, i) => set(0x04 + i, c));
  "1234567890".split("").forEach((c, i) => set(0x1e + i, c));
  [[0x28, "Enter"], [0x29, "Esc"], [0x2a, "Bksp"], [0x2b, "Tab"], [0x2c, "Space"], [0x2d, "-"], [0x2e, "="], [0x2f, "["],
   [0x30, "]"], [0x31, "\\"], [0x32, "#"], [0x33, ";"], [0x34, "'"], [0x35, "`"], [0x36, ","], [0x37, "."], [0x38, "/"],
   [0x39, "Caps"], [0x46, "PrtSc"], [0x47, "ScrLk"], [0x48, "Pause"], [0x49, "Ins"], [0x4a, "Home"], [0x4b, "PgUp"],
   [0x4c, "Del"], [0x4d, "End"], [0x4e, "PgDn"], [0x4f, "→"], [0x50, "←"], [0x51, "↓"], [0x52, "↑"], [0x53, "NumLk"],
   [0x54, "KP /"], [0x55, "KP *"], [0x56, "KP -"], [0x57, "KP +"], [0x58, "KP Ent"], [0x62, "KP 0"], [0x63, "KP ."], [0x65, "Menu"],
   [0xa8, "Mute"], [0xa9, "Vol +"], [0xaa, "Vol −"], [0xab, "Next"], [0xac, "Prev"], [0xad, "Stop"], [0xae, "Play"],
   [0xcd, "Mouse ↑"], [0xce, "Mouse ↓"], [0xcf, "Mouse ←"], [0xd0, "Mouse →"],
   [0xd9, "Scroll ↑"], [0xda, "Scroll ↓"], [0xdb, "Scroll ←"], [0xdc, "Scroll →"],
   [0xe0, "L Ctrl"], [0xe1, "L Shift"], [0xe2, "L Alt"], [0xe3, "L GUI"], [0xe4, "R Ctrl"], [0xe5, "R Shift"], [0xe6, "R Alt"], [0xe7, "R GUI"],
  ].forEach(([v, n]) => set(v, n));
  for (let i = 0; i < 9; i++) set(0x59 + i, "KP " + (i + 1));
  for (let i = 0; i < 12; i++) { set(0x3a + i, "F" + (i + 1)); set(0x68 + i, "F" + (i + 13)); }
  for (let i = 0; i < 8; i++) set(0xd1 + i, "Mouse " + (i + 1));

  const WM0 = 0x7e00, LAYER = { 0x5200: "TO", 0x5220: "MO", 0x5240: "DF", 0x5260: "TG", 0x5280: "OSL", 0x52c0: "TT" };
  const MODS = [[1, "Ctrl"], [2, "Shift"], [4, "Alt"], [8, "GUI"]];

  function name(kc) {
    if (kc == null) return "?";
    if (kc === 0) return "✕";
    if (kc === 1) return "▽";
    if (kc >= WM0 && kc < WM0 + 32) return "WM" + String(kc - WM0 + 1).padStart(2, "0");
    if (kc <= 0xff) return basic[kc] || "0x" + kc.toString(16);
    if (kc >= 0x5200 && kc < 0x5300) {
      const base = kc & 0xffe0;
      if (LAYER[base]) return `${LAYER[base]}(${(kc & 0x1f) + 1})`;
    }
    if (kc >= 0x4000 && kc < 0x5000) return `LT(${((kc >> 8) & 0xf) + 1}, ${basic[kc & 0xff] || "?"})`;
    if (kc >= 0x0100 && kc < 0x2000) {
      const m = (kc >> 8) & 0x1f, right = m & 0x10 ? "R" : "";
      return MODS.filter(([b]) => m & b).map(([, n]) => right + n).join("+") + "+" + (basic[kc & 0xff] || "?");
    }
    if (kc === 0x7c00) return "Boot";
    if (kc >= 0x7700 && kc < 0x7720) return "M" + (kc - 0x7700);
    if (kc >= 0x5700 && kc < 0x5720) return `TD(${kc - 0x5700})`;
    return "0x" + kc.toString(16).padStart(4, "0");
  }
  const isWM = (kc) => kc >= WM0 && kc < WM0 + 32;
  const range = (a, b) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
  const groups = [
    ["WINGMACRO", range(WM0, WM0 + 31)],
    ["LETTERS", range(0x04, 0x27)],
    ["F-KEYS", [...range(0x3a, 0x45), ...range(0x68, 0x73)]],
    ["EDIT / NAV", [0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x39, ...range(0x2d, 0x38), ...range(0x46, 0x53), 0x65]],
    ["NUMPAD", range(0x54, 0x63)],
    ["MODIFIERS", range(0xe0, 0xe7)],
    ["MEDIA", range(0xa8, 0xae)],
    ["MOUSE", [...range(0xd9, 0xdc), ...range(0xd1, 0xd5), ...range(0xcd, 0xd0)]],
    ["LAYERS", [0x5200, 0x5201, 0x5202, 0x5203, 0x5220, 0x5221, 0x5222, 0x5223, 0x5260, 0x5261, 0x5262, 0x5263,
      0x5280, 0x5281, 0x5282, 0x5283, 0x52c0, 0x52c1, 0x52c2, 0x52c3]],
    ["KEY MACROS", range(0x7700, 0x770f)],
    ["TAP DANCE", range(0x5700, 0x571f)],
    ["SPECIAL", [1, 0]],
  ];
  return { name, isWM, groups, MODS, WM0 };
})();
