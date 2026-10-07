"use strict";
// wingmacro UI: pad view + mapping editor, macros, console connection, setup.
// Config schema: docs/config-model.md. Every edit autosaves (debounced) to /api/config.

// ---------------------------------------------------------------------------- state
const S = {
  cfg: null, strips: null, pad: null, fx: {}, fxParams: {}, live: null,
  page: "pad", layer: 0, follow: true, selectOnPress: true,
  sel: null,            // {kind:"key", idx} | {kind:"knob", knob}
  macroSel: null, consoles: null, scanning: false,
  km: null, kmSel: null, kmSlot: "push", kmTab: "WINGMACRO", kmMods: 0, kmErr: "",
};
// WING strip colours, sampled from Wing Edit (2026-10-07). The console palette has 12; 13-18 look reserved and display like 12.
const WCOL = [null, "#203a64", "#00527f", "#23007f", "#00686a", "#005f1f", "#414c00", "#736b00", "#5e310d",
  "#720020", "#7f2f2f", "#7f007e", "#4f007f", "#4f007f", "#4f007f", "#4f007f", "#4f007f", "#4f007f", "#4f007f"];
// LED colours: the WING's 12 in its picker order (1-12) + white + off, as LED HSV. Swatches show the LED
// colour (not the WING's screen shade), tuned on the pad: orange = case/UI amber, red = true red.
// Keep in sync with config.py. Older names (crimson, amber, cyan, blue) are still accepted.
const SWATCHES = [
  ["steel", [150, 160, 200]],
  ["sky", [140, 255, 200]],
  ["indigo", [178, 255, 200]],
  ["teal", [128, 255, 200]],
  ["green", [85, 255, 200]],
  ["olive", [55, 255, 200]],
  ["yellow", [40, 255, 200]],
  ["orange", [22, 255, 200]],
  ["red", [0, 255, 200]],
  ["coral", [5, 150, 200]],
  ["magenta", [213, 255, 200]],
  ["purple", [192, 255, 200]],
  ["white", [0, 0, 200]], ["off", [0, 0, 0]]].map(([n, c]) => [n, c, n === "off" ? "#000" : hsvCss(c)]);
const PALETTE = { ...Object.fromEntries(SWATCHES.map(([n, c]) => [n, c])),
  crimson: [0, 255, 200], amber: [22, 255, 200], cyan: [128, 255, 200], blue: [170, 255, 200] };
const SWATCH_RGB = Object.fromEntries(SWATCHES.map(([n, , rgb]) => [n, rgb]));
const KINDS = [["ch", "CH", 40], ["aux", "AUX", 8], ["bus", "BUS", 16], ["main", "MAIN", 4],
  ["mtx", "MTX", 8], ["dca", "DCA", 16]];

const ACT = {
  mute:      { label: "Mute", g: "Mutes", f: [["target", "target"], ["op", "op"]] },
  softmute:  { label: "Soft mute", g: "Mutes", f: [["target", "target"], ["op", "opsoft"], ["time", "num", { unit: "s", def: 5, step: 0.5, min: 0 }]] },
  mgrp:      { label: "Mute group", g: "Mutes", f: [["n", "mgrp"], ["op", "op"]] },
  level_set: { label: "Set level", g: "Levels", f: [["target", "target"], ["db", "db"]] },
  level:     { label: "Level", g: "Levels", rot: true, f: [["target", "target"], ["step", "num", { unit: "dB", ph: "0.1", step: 0.1, min: 0 }]] },
  gain:      { label: "Input gain", g: "Levels", rot: true, f: [["target", "targetch"], ["step", "num", { unit: "dB", ph: "0.5", step: 0.5, min: 0 }]] },
  fx:        { label: "FX parameter", g: "Effects", rot: true, f: [["slot", "fxslot"], ["param", "fxparam"], ["step", "num", { ph: "auto", step: 0.01, min: 0 }]] },
  fx_cycle:  { label: "FX option (cycle)", g: "Effects", rot: true, both: true, f: [["slot", "fxslot"], ["param", "fxenum"], ["dir", "dir"]] },
  fx_set:    { label: "Set FX parameter", g: "Effects", f: [["slot", "fxslot"], ["param", "fxparam"], ["value", "fxvalue"]] },
  tap:       { label: "Tap tempo", g: "Effects", f: [["slots", "fxslots"], ["window", "num", { ph: "4", step: 1, min: 1 }]] },
  led:       { label: "Key LED", g: "Pad", f: [["colour", "ledcolour"], ["effect", "effect"], ["key", "ledtarget"]] },
  wait:      { label: "Wait", g: "System", f: [["ms", "num", { unit: "ms", def: 500, step: 50, min: 0 }]] },
  refresh:   { label: "Refresh console", g: "System", f: [] },
  set:       { label: "Raw set (advanced)", g: "System", f: [["path", "text", { ph: "/ch/1/eq/on" }], ["value", "text", { ph: "1" }]] },
};

// ---------------------------------------------------------------------------- helpers
function h(tag, a, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(a || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(9)) if (c != null && c !== false) e.append(c.nodeType ? c : String(c));
  return e;
}
const $ = (id) => document.getElementById(id);
const clone = (o) => JSON.parse(JSON.stringify(o));
const api = async (path, opt) => { const r = await fetch(path, opt); return r.json(); };
function hsvCss(c, boost = true) {
  if (!c) return "transparent";
  let [hh, s, v] = c; hh = hh / 255 * 360; s /= 255; v = Math.min(1, v / (boost ? 200 : 255));
  const f = (n) => { const k = (n + hh / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return `rgb(${[f(5), f(3), f(1)].map((x) => Math.round(x * 255)).join(",")})`;
}
const colourOf = (c) => (typeof c === "string" ? PALETTE[c] : c);
const sameCol = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function seg(options, value, onPick, cls = "") {
  return h("div", { class: "seg " + cls }, options.map(([v, label]) =>
    h("button", { class: sameCol(v, value) ? "on" : "", onclick: () => onPick(v) }, label)));
}
function field(label, ...el) { return h("label", { class: "f" }, label, ...el); }
function sect(title, ...kids) { return h("div", { class: "sect" }, h("h4", {}, title), ...kids); }
function panel(title, body, opts = {}) {
  return h("section", { class: "panel " + (opts.cls || ""), style: opts.style },
    h("div", { class: "phead" }, opts.left && h("div", { class: "left" }, opts.left), title,
      opts.right && h("div", { class: "right" }, opts.right)),
    h("div", { class: "pbody " + (opts.bodyCls || "") }, body));
}
const icon = {
  up: '<svg viewBox="0 0 24 24"><path d="M6 15l6-6 6 6"/></svg>',
  down: '<svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};
const iconBtn = (name, onclick, title) => { const b = h("button", { class: "btn icon", onclick, title }); b.innerHTML = icon[name]; return b; };

// ---------------------------------------------------------------------------- config access
function layerCfg(l, create) {
  const L = S.cfg.layers;
  if (!L[l] && create) L[l] = { buttons: {}, encoders: {} };
  const o = L[l];
  if (o && create) { o.buttons ||= {}; o.encoders ||= {}; }
  return o;
}
function lookup(kind, key, layer) {           // with fallback to lower layers
  for (let l = layer; l >= 0; l--) {
    const m = S.cfg.layers[l]?.[kind]?.[key];
    if (m) return { m, from: l };
  }
  return { m: null, from: null };
}
function wmAt(layer, idx) { return S.pad?.layers?.[layer]?.[idx] ?? idx + 1; }

let saveT = null;
function save() {
  const st = $("save-state"); st.className = "savestate"; st.textContent = "Saving…";
  clearTimeout(saveT);
  saveT = setTimeout(async () => {
    const r = await api("/api/config", { method: "PUT", body: JSON.stringify(S.cfg) }).catch((e) => ({ ok: false, error: String(e) }));
    st.className = "savestate" + (r.ok ? "" : " err");
    st.textContent = r.ok ? "Saved" : "Not saved: " + r.error;
    st.title = r.ok ? "" : r.error;
  }, 350);
}
function commit(rerender = true) { save(); if (rerender) render(); }

// ---------------------------------------------------------------------------- names
function parseTarget(t) {
  if (!t) return null;
  const p = t.replace(/^\//, "").split("/");
  return p[2] === "send" ? { kind: p[0], n: +p[1], bus: +p[3] } : { kind: p[0], n: +p[1] };
}
function stripInfo(kind, n) { return S.strips?.[kind]?.[n - 1] || { name: "", col: null }; }
function stripCap(kind, n) { return `${kind.toUpperCase()}.${n}`; }
function targetLabel(t) {
  const p = parseTarget(t);
  if (!p) return { cap: "—", name: "Choose…", col: null };
  const s = stripInfo(p.kind, p.n);
  if (p.bus) {
    const b = stripInfo("bus", p.bus);
    return { cap: `${stripCap(p.kind, p.n)}→BUS.${p.bus}`, name: `${s.name || stripCap(p.kind, p.n)} → ${b.name || "BUS " + p.bus}`, col: s.col };
  }
  return { cap: stripCap(p.kind, p.n), name: s.name || stripCap(p.kind, p.n), col: s.col };
}
function fxName(slot) { const m = S.fx[slot]; return m && m !== "NONE" ? m : "empty"; }
function macroNames() { return Object.keys(S.cfg.macros || {}); }

function firstSteps(doV) {
  if (typeof doV === "string") return S.cfg.macros?.[doV]?.steps || [];
  if (doV && doV.toggle) return firstSteps(doV.toggle[0]);
  return doV || [];
}
function summary(m) {                       // -> {cap, col, name, act}
  if (!m) return { cap: "", name: "", act: "" };
  const doV = m.do;
  let r = { cap: "", col: null, name: "", act: "" };
  const st = firstSteps(doV)[0];
  if (st) {
    const t = st.target && targetLabel(st.target);
    switch (st.do) {
      case "mute": r = { cap: t.cap, col: t.col, name: t.name, act: "Mute" }; break;
      case "softmute": r = { cap: t.cap, col: t.col, name: t.name, act: `Soft mute ${st.time ?? 5}s` }; break;
      case "mgrp": r = { cap: `MGRP.${st.n}`, name: stripInfo("mgrp", st.n).name || `Mute grp ${st.n}`, act: "Mute group" }; break;
      case "level_set": r = { cap: t.cap, col: t.col, name: t.name, act: `Set ${st.db === "-inf" ? "−∞" : (st.db ?? 0) + " dB"}` }; break;
      case "tap": r = { cap: "FX." + (st.slots || []).join(","), name: "Tap", act: "Tap tempo" }; break;
      case "fx_set": case "fx_cycle": r = { cap: `FX.${st.slot}`, name: st.param || "", act: ACT[st.do].label }; break;
      default: r = { cap: "", name: ACT[st.do]?.label || st.do, act: "" };
    }
  }
  if (typeof doV === "string") { r.name = doV; r.act = "Macro"; r.cap ||= "MACRO"; }
  if (doV && doV.toggle) r.act = "A/B " + r.act;
  if (m.name) r.name = m.name;
  if (m.trigger === "hold") r.act = "Hold · " + r.act;
  if (m.trigger === "momentary") r.act = "While held · " + r.act;
  return r;
}
function rotSummary(steps) {
  const st = steps?.[0]; if (!st) return "";
  if (st.do === "fx" || st.do === "fx_cycle") return `FX${st.slot} ${st.param || ""}`;
  if (st.target) return `${ACT[st.do].label} ${targetLabel(st.target).name}`;
  return ACT[st.do]?.label || "";
}

// ---------------------------------------------------------------------------- top bar
function renderTop() {
  const L = S.live;
  $("wing-dot").className = "dot" + (L?.wing.connected ? " on" : "");
  $("wing-label").textContent = L?.wing.connected ? `${L.wing.info?.name || "WING"} ${L.wing.host}` : (L?.wing.host ? "WING …" : "WING searching");
  $("pad-dot").className = "dot" + (L?.pad.connected ? " on" : "");
  $("pad-layer").textContent = L?.pad.connected ? L.pad.layer + 1 : "–";
  const bar = $("selbar");
  let num = "—", name = "No control selected", col = null, mapped = false;
  if (S.page === "pad" && S.sel) {
    if (S.sel.kind === "key") {
      const wm = wmAt(S.layer, S.sel.idx);
      const { m } = lookup("buttons", wm, S.layer);
      const s = summary(m);
      num = `L${S.layer + 1} · ${S.sel.idx + 1}`; name = m ? s.name || s.act : wm ? `WM${wm} · not mapped` : "Not a WM key";
      col = s.col; mapped = !!m;
    } else {
      const { m } = lookup("encoders", S.sel.knob, S.layer);
      num = `L${S.layer + 1} · ${S.sel.knob === "left" ? "KNOB L" : "KNOB R"}`; name = m ? m.name || rotSummary(m.turn) || "Knob" : "not mapped";
      mapped = !!m;
    }
  } else if (S.page === "macros" && S.macroSel) { num = "MACRO"; name = S.macroSel; mapped = true; }
  bar.className = "selbar" + (mapped ? " mapped" : "");
  bar.style.background = col ? WCOL[col] : "";
  bar.querySelector(".selnum").textContent = num;
  bar.querySelector(".selname").textContent = name;
}

// ---------------------------------------------------------------------------- pad page
function renderPad() {
  const live = S.live, onLive = live?.pad.connected && live.pad.layer === S.layer;
  const banks = h("div", { class: "banks" },
    [0, 1, 2, 3].map((l) => h("button", {
      class: "btn light" + (S.layer === l ? " on" : ""),
      onclick: () => pickLayer(l),
    }, `LAYER ${l + 1}`)),
    h("div", { class: "follow" },
      h("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:6px" },
        toggleBtn("LINK TO PAD", S.follow, (v) => { S.follow = v; if (v && live) S.layer = live.pad.layer; render(); }),
        toggleBtn("SELECT ON PRESS", S.selectOnPress, (v) => { S.selectOnPress = v; render(); }))));

  const keys = h("div", { class: "keys" }, [...Array(16).keys()].map((idx) => {
    const wm = wmAt(S.layer, idx);
    if (!wm) {
      const kc = effectiveKc(S.layer, Math.floor(idx / 4), idx % 4);
      return h("div", { class: "key nowm", "data-idx": idx, title: "Ordinary key (set on the Keymap page)" },
        h("span", { class: "nm" }, kc == null ? "Key" : KC.name(kc)), h("span", { class: "act" }, "not WM"));
    }
    const { m, from } = lookup("buttons", wm, S.layer);
    const s = summary(m);
    const led = onLive && live.leds ? live.leds[idx] : null;
    return h("button", {
      class: "key" + (S.sel?.kind === "key" && S.sel.idx === idx ? " sel" : "") + (m && from !== S.layer ? " inherit" : "") + (m ? "" : " empty"),
      "data-idx": idx, title: `Key ${idx + 1} · WM${String(wm).padStart(2, "0")}`, onclick: () => { S.sel = { kind: "key", idx }; render(); },
      style: led ? `--led:${hsvCss(led)}` : "",
    },
      h("span", { class: "cap", style: s.col ? `background:${WCOL[s.col]}` : (s.cap ? "" : "visibility:hidden") }, s.cap || "·"),
      h("span", { class: "nm" }, m ? s.name : "—"),
      h("span", { class: "act" }, s.act),
      m && from !== S.layer && h("span", { class: "badge" }, `L${from + 1}`),
      h("span", { class: "wm" }, String(wm).padStart(2, "0")));
  }));

  const knob = (k) => {
    const { m, from } = lookup("encoders", k, S.layer);
    return h("button", { class: "knob" + (S.sel?.kind === "knob" && S.sel.knob === k ? " sel" : "") + (m ? " mapped" : "") + (m && from !== S.layer ? " inherit" : ""),
      "data-knob": k, title: `${k === "left" ? "Left" : "Right"} knob${m && from !== S.layer ? ` (from layer ${from + 1})` : ""}`,
      onclick: () => { S.sel = { kind: "knob", knob: k }; render(); } },
      dial(), h("span", { class: "kl" }, m ? (m.name || rotSummary(m.turn) || "Knob") : "—"));
  };
  const padBody = h("div", { class: "doio" },          // positions measured from a photo of the KB16
    h("div", { class: "well" }, keys), knob("left"), knob("right"),
    h("div", { class: "bigknob", title: "Big knob: mouse wheel on every layer (not mapped here)" }, h("i"), h("span", {}, "SCROLL")));
  const legend = h("div", { class: "legend" },
    h("span", {}, h("i"), "Mapped here"), h("span", {}, h("i", { class: "d" }), "Inherited from a lower layer"),
    h("span", {}, "Glow = live LED (pad on this layer)"),
    !S.pad?.known && h("span", { style: "color:var(--amber)" }, "Pad keymap unknown: assuming WM01–16"));

  return h("div", { class: "cols padpage" },
    h("section", { class: "panel" }, h("div", { class: "phead" }, "LAYERS"), banks),
    panel("PAD", h("div", { class: "padwrap" }, padBody, legend)),
    h("section", { class: "panel" }, editorFor()));
}
// Layer tabs: when linked to the pad, picking a layer also moves the pad (and vice versa).
async function pickLayer(l) {
  S.layer = l;
  if (S.follow && S.live?.pad.connected) {
    if ((S.live.pad.proto || 0) >= 2) {
      const r = await api("/api/pad/layer", { method: "POST", body: JSON.stringify({ layer: l }) }).catch(() => ({ ok: false }));
      if (r.ok) S.live.pad.layer = l;
    } else S.follow = false;        // old firmware: can't move the pad, so unlink instead
  }
  render();
}
function toggleBtn(label, on, set) {      // WING-style labelled switch
  return h("button", { class: "switch" + (on ? " on" : ""), onclick: () => set(!on) },
    h("span", { class: "sl" }, label), h("span", { class: "sk" }, h("i"), on ? "ON" : "OFF"));
}
function dial() {
  const d = h("div", { class: "dial" }); d.innerHTML = '<svg viewBox="0 0 70 70"><path d="M17 55 A26 26 0 1 1 53 55"/></svg>'; return d;
}

function editorFor() {
  if (!S.sel) return h("div", { class: "editor-empty" }, "Select a key or knob", h("br"), h("span", { class: "hint" }, "or press one on the pad"));
  return S.sel.kind === "key" ? keyEditor(S.sel.idx) : knobEditor(S.sel.knob);
}

function inheritBar(kind, key, from, title) {
  return h("div", { class: "pbody" },
    h("p", {}, `${title} is mapped on layer ${from + 1} and passes through to layer ${S.layer + 1}.`),
    h("div", { class: "row" },
      h("button", { class: "btn amber", onclick: () => { layerCfg(S.layer, true)[kind][key] = clone(S.cfg.layers[from][kind][key]); commit(); } }, "Override on this layer"),
      h("button", { class: "btn", onclick: () => { S.layer = from; S.follow = false; render(); } }, `Edit on layer ${from + 1}`)));
}

function keyEditor(idx) {
  const wm = wmAt(S.layer, idx);
  const head = (right) => h("div", { class: "phead" }, `KEY ${idx + 1}${wm ? " · WM" + String(wm).padStart(2, "0") : ""} · LAYER ${S.layer + 1}`,
    right && h("div", { class: "right" }, right));
  if (!wm) return [head(), h("div", { class: "pbody" }, h("p", {}, "This key isn't a WM key in Vial, so it acts as an ordinary key (e.g. a shortcut for Wing Edit)."),
    h("p", { class: "hint" }, "To map it here, assign it a WM keycode on Vial's User tab."))];
  const { m, from } = lookup("buttons", wm, S.layer);
  if (m && from !== S.layer) return [head(), inheritBar("buttons", wm, from, `WM${wm}`)];
  if (!m) return [head(), h("div", { class: "pbody" }, h("p", { class: "muted" }, "Not mapped on this layer."),
    h("button", { class: "btn amber", onclick: () => { layerCfg(S.layer, true).buttons[wm] = { trigger: "press", do: [] }; commit(); } }, "Create mapping"))];

  const pad = S.cfg.pad || {};
  const body = h("div", { class: "pbody" },
    sect("Name", h("input", { type: "text", value: m.name || "", placeholder: summary({ ...m, name: "" }).name || "Label shown on the pad view",
      oninput: (e) => { m.name = e.target.value || undefined; commit(false); renderTop(); }, onchange: () => render() })),
    sect("Trigger",
      h("div", { class: "row" },
        seg([["momentary", "Momentary"], ["press", "Press"], ["hold", "Hold"]], m.trigger || "press", (v) => {
          m.trigger = v; if (v === "momentary" && m.do?.toggle) m.do = m.do.toggle[0]; commit(); }, "fixed"),
        // always laid out, hidden unless Hold, so the row never shifts
        h("div", { class: "row", style: m.trigger === "hold" ? "" : "visibility:hidden" },
          field("Hold time", h("span", {}, numInput(m.hold_ms, (v) => { m.hold_ms = v; }, { ph: pad.hold_ms ?? 800, step: 50, min: 100 }), h("span", { class: "unit" }, "ms"))),
          field("Cancel window", h("span", {}, numInput(m.cancel_ms, (v) => { m.cancel_ms = v; }, { ph: pad.cancel_ms ?? 400, step: 50, min: 0 }), h("span", { class: "unit" }, "ms"))))),
      h("p", { class: "hint", style: "min-height:2.6em" }, {
        hold: "Hold until the key lights fully, then release. It flashes while armed; tap it again within the cancel window to cancel.",
        momentary: "Acts the moment the key goes down and stays active while held (e.g. talkback). On release, everything it changed is put back and soft mutes fade back.",
      }[m.trigger] || "Fires when the key is released.")),
    sect("Action", doEditor(() => m.do, (v) => { m.do = v; }, wm, m.trigger === "momentary")),
    sect("LED", h("p", { class: "hint" }, "Key colour is the key's resting colour. Macros change it with the Key LED action, e.g. a dim red here and full red in the macro."),
      field("Key colour", colourPicker(m.background, (v) => { m.background = v; }, { allowNone: true, noneLabel: "Pad background" })),
      h("div", { style: "height:10px" }),
      field("Fire animation", seg([["none", "None"], ["flash", "Flash"], ["burst", "Flash + burst"]],
        m.fire_anim || (m.trigger === "hold" ? "flash" : "none"), (v) => { m.fire_anim = v; commit(); }, "sm")),
      h("p", { class: "hint" }, "Plays when the key fires. Burst sends a ring of light out across the pad."),
      field("Animation colour", colourPicker(m.hold_colour, (v) => { m.hold_colour = v; }, { allowNone: true, noneLabel: "White (default)" })),
      h("p", { class: "hint" }, "Used for the fire animation and, on hold keys, the glow while held.")));
  return [head(h("button", { class: "btn sm danger", onclick: () => { delete layerCfg(S.layer).buttons[wm]; commit(); } }, "Clear")), body];
}

function knobEditor(knob) {
  const title = knob === "left" ? "LEFT KNOB" : "RIGHT KNOB";
  const head = (right) => h("div", { class: "phead" }, `${title} · LAYER ${S.layer + 1}`, right && h("div", { class: "right" }, right));
  const { m, from } = lookup("encoders", knob, S.layer);
  if (m && from !== S.layer) return [head(), inheritBar("encoders", knob, from, title.toLowerCase())];
  if (!m) return [head(), h("div", { class: "pbody" }, h("p", { class: "muted" }, "Not mapped on this layer."),
    h("button", { class: "btn amber", onclick: () => { layerCfg(S.layer, true).encoders[knob] = { turn: [] }; commit(); } }, "Create mapping"))];
  const body = h("div", { class: "pbody" },
    sect("Name", h("input", { type: "text", value: m.name || "", placeholder: rotSummary(m.turn) || "Label",
      oninput: (e) => { m.name = e.target.value || undefined; commit(false); renderTop(); }, onchange: () => render() })),
    sect("Turn",
      h("div", { class: "row", style: "margin-bottom:8px" }, field("Acceleration",
        seg([["off", "Off"], ["fine", "Fine"], ["normal", "Normal"]], m.accel || "fine", (v) => { m.accel = v; commit(); }, "sm"))),
      stepList(m.turn ||= [], true)),
    sect("Push + turn", h("p", { class: "hint" }, "Used while the knob is held down. Leave empty to use Turn."),
      stepList(m.push_turn ||= [], true)),
    sect("Push (no turn)", h("p", { class: "hint" }, "Fires on release, only if the knob wasn't turned while held."),
      m.push ? doEditor(() => m.push.do, (v) => { m.push.do = v; }, knob)
        : h("button", { class: "btn", onclick: () => { m.push = { trigger: "press", do: [] }; commit(); } }, "+ Add push action"),
      m.push && h("button", { class: "btn sm ghost", style: "margin-top:6px", onclick: () => { delete m.push; commit(); } }, "Remove push action")));
  return [head(h("button", { class: "btn sm danger", onclick: () => { delete layerCfg(S.layer).encoders[knob]; commit(); } }, "Clear")), body];
}

// ---------------------------------------------------------------------------- do / steps
function doEditor(get, set, key, noToggle) {
  const v = get();
  const mode = typeof v === "string" ? "macro" : v && v.toggle ? "toggle" : "steps";
  const modes = [["steps", "Actions"], ["macro", "Macro"], ...(noToggle ? [] : [["toggle", "Toggle A/B"]])];
  const modeSeg = seg(modes, mode, (nv) => {
    if (nv === mode) return;
    if (nv === "steps") set(typeof v === "string" ? clone(S.cfg.macros?.[v]?.steps || []) : []);
    if (nv === "macro") set(macroNames()[0] || newMacro());
    if (nv === "toggle") set({ toggle: [Array.isArray(v) ? v : [], []] });
    commit();
  }, "sm");
  let inner;
  if (mode === "steps") inner = stepList(v, false);
  else if (mode === "macro") inner = macroPick(v, set);
  else inner = h("div", {}, ["A · 1st press", "B · 2nd press"].map((lbl, i) => {
    const sub = v.toggle[i];
    const subMode = typeof sub === "string" ? "macro" : "steps";
    return h("div", { style: "margin:8px 0 10px" },
      h("div", { class: "row", style: "margin-bottom:6px;align-items:center" }, h("b", { style: "color:var(--amber)" }, lbl),
        seg([["steps", "Actions"], ["macro", "Macro"]], subMode, (nv) => {
          if (nv !== subMode) { v.toggle[i] = nv === "macro" ? (macroNames()[0] || newMacro()) : []; commit(); }
        }, "sm")),
      subMode === "macro" ? macroPick(sub, (nv) => { v.toggle[i] = nv; }) : stepList(sub, false));
  }), h("p", { class: "hint" }, "Each press alternates between A and B."));
  return h("div", {}, h("div", { style: "margin-bottom:8px" }, modeSeg), inner);
}
function macroPick(name, set) {
  return h("div", { class: "row" },
    h("select", { onchange: (e) => { set(e.target.value); commit(); } },
      macroNames().map((n) => h("option", { value: n, selected: n === name }, n))),
    h("button", { class: "btn sm", onclick: () => { S.macroSel = name; go("macros"); } }, "Edit macro"),
    h("button", { class: "btn sm ghost", onclick: () => { set(newMacro()); commit(); } }, "+ New"));
}
function newMacro() {
  S.cfg.macros ||= {};
  let i = 1; while (S.cfg.macros["Macro " + i]) i++;
  S.cfg.macros["Macro " + i] = { steps: [] };
  return "Macro " + i;
}

function stepList(steps, rotary) {
  const allowed = Object.entries(ACT).filter(([, a]) => (rotary ? a.rot : !a.rot || a.both));
  const add = h("select", { class: "btn", onchange: (e) => {
    const d = e.target.value; if (!d) return;
    const st = { do: d };
    for (const [k, t, o] of ACT[d].f) {
      if (o?.def != null) st[k] = o.def;
      if (t === "op") st[k] = "toggle";
      if (t === "opsoft") st[k] = "toggle";
      if (t === "fxslot") st[k] = firstFxSlot();
      if (t === "fxslots") st[k] = [];
      if (t === "mgrp") st[k] = 1;
      if (t === "dir" && !rotary) st[k] = "next";
      if (t === "ledcolour") st[k] = "green";
    }
    steps.push(st); commit();
  } }, h("option", { value: "" }, rotary ? "+ Add rotary action" : "+ Add action"),
  groupBy(allowed).map(([g, list]) => h("optgroup", { label: g }, list.map(([k, a]) => h("option", { value: k }, a.label)))));
  return h("div", {},
    h("div", { class: "steps" }, steps.length ? steps.map((st, i) => stepRow(steps, st, i, rotary)) : h("div", { class: "hint" }, "No actions yet.")),
    h("div", { class: "addrow" }, add));
}
function groupBy(entries) {
  const g = {}; for (const e of entries) (g[e[1].g] ||= []).push(e); return Object.entries(g);
}
function firstFxSlot() { const s = Object.keys(S.fx).find((k) => S.fx[k] && S.fx[k] !== "NONE"); return s ? +s : 1; }

function stepRow(steps, st, i, rotary) {
  const a = ACT[st.do] || { label: st.do, f: [] };
  const fields = a.f.filter(([, t]) => !(t === "dir" && rotary)).map(([k, t, o]) => fieldFor(st, k, t, o || {}));
  return h("div", { class: "step" + (st.do === "wait" ? " wait" : "") },
    h("div", { class: "no" }, i + 1),
    h("div", {}, h("div", { style: "font-weight:600;text-transform:uppercase;margin-bottom:6px" }, a.label),
      h("div", { class: "row" }, fields)),
    h("div", { class: "row", style: "gap:4px;flex-wrap:nowrap" },
      iconBtn("up", () => { if (i) { [steps[i - 1], steps[i]] = [steps[i], steps[i - 1]]; commit(); } }, "Move up"),
      iconBtn("down", () => { if (i < steps.length - 1) { [steps[i + 1], steps[i]] = [steps[i], steps[i + 1]]; commit(); } }, "Move down"),
      iconBtn("x", () => { steps.splice(i, 1); commit(); }, "Remove")));
}

function numInput(val, set, o = {}) {
  return h("input", { type: "number", value: val ?? "", placeholder: o.ph ?? "", step: o.step ?? "any", min: o.min,
    oninput: (e) => { const v = e.target.value; set(v === "" ? undefined : +v); commit(false); } });
}

function fieldFor(st, k, t, o) {
  switch (t) {
    case "target": case "targetch":
      return field(t === "targetch" ? "Channel" : "Target", targetBtn(st[k], (v) => { st[k] = v; commit(); }, t === "targetch"));
    case "op": return field("Mode", seg([["toggle", "Toggle"], ["on", "On"], ["off", "Off"]], st[k] || "toggle", (v) => { st[k] = v; commit(); }, "sm"));
    case "opsoft": return field("Mode", seg([["toggle", "Toggle"], ["down", "Fade out"], ["up", "Fade in"]], st[k] || "toggle", (v) => { st[k] = v; commit(); }, "sm"));
    case "dir": return field("Direction", seg([["next", "Next"], ["prev", "Prev"]], st[k] || "next", (v) => { st[k] = v; commit(); }, "sm"));
    case "num": return field(k === "step" ? "Step" : k === "time" ? "Fade time" : k, h("span", {}, numInput(st[k], (v) => { st[k] = v; }, o), o.unit && h("span", { class: "unit" }, o.unit)));
    case "text": return field(k, h("input", { type: "text", value: st[k] ?? "", placeholder: o.ph,
      oninput: (e) => { const v = e.target.value; st[k] = k === "value" && v !== "" && !isNaN(+v) ? +v : v; commit(false); } }));
    case "db": {
      const inf = st[k] === "-inf";
      return field("Level", h("span", { class: "row", style: "gap:6px;align-items:center" },
        !inf && numInput(st[k] ?? 0, (v) => { st[k] = v ?? 0; }, { step: 0.1, min: -89.5, max: 10 }), !inf && h("span", { class: "unit" }, "dB"),
        seg([[false, "dB"], [true, "−∞"]], inf, (v) => { st[k] = v ? "-inf" : 0; commit(); }, "sm")));
    }
    case "mgrp": return field("Group", h("select", { onchange: (e) => { st[k] = +e.target.value; commit(); } },
      [1, 2, 3, 4, 5, 6, 7, 8].map((n) => h("option", { value: n, selected: st[k] === n }, `${n}${stripInfo("mgrp", n).name ? " · " + stripInfo("mgrp", n).name : ""}`))));
    case "fxslot": return field("FX slot", fxSlotSelect(st[k], (v) => { st[k] = v; delete st.param; delete st.value; commit(); }));
    case "fxslots": return field("FX slots", h("div", { class: "row", style: "gap:4px" }, [...Array(16).keys()].map((i) => {
      const n = i + 1, on = (st[k] || []).includes(n);
      return h("button", { class: "btn sm" + (on ? " amber" : ""), title: fxName(n),
        onclick: () => { st[k] = on ? st[k].filter((x) => x !== n) : [...(st[k] || []), n].sort((a, b) => a - b); commit(); } },
        `${n}${S.fx[n] && S.fx[n] !== "NONE" ? " " + S.fx[n] : ""}`);
    })));
    case "fxparam": case "fxenum": return field("Parameter", fxParamSelect(st, t === "fxenum"));
    case "fxvalue": return field("Value", fxValueInput(st));
    case "ledcolour": return field("Colour", colourPicker(st[k] === "base" ? undefined : st[k], (v) => { st[k] = v ?? "base"; }, { allowNone: true, noneLabel: "Back to the key's own colour" }));
    case "effect": return field("Effect", seg([["solid", "Solid"], ["flash", "Flash"], ["pulse", "Pulse"]], st[k] || "solid", (v) => { st[k] = v; commit(); }, "sm"));
    case "ledtarget": {
      const own = !st.key;
      return field("Key", h("div", { class: "row", style: "gap:6px;align-items:center" },
        seg([[true, "This key"], [false, "Other key"]], own, (v) => { if (v) { delete st.key; delete st.layer; } else { st.key = 1; st.layer = S.layer + 1; } commit(); }, "sm"),
        !own && h("select", { onchange: (e) => { st.layer = +e.target.value; commit(); } }, [1, 2, 3, 4].map((l) => h("option", { value: l, selected: (st.layer || 1) === l }, `Layer ${l}`))),
        !own && h("select", { onchange: (e) => { st.key = +e.target.value; commit(); } }, [...Array(16).keys()].map((i) => h("option", { value: i + 1, selected: st.key === i + 1 }, `Key ${i + 1}`)))));
    }
  }
  return null;
}
function fxSlotSelect(val, set) {
  return h("select", { onchange: (e) => set(+e.target.value) },
    [...Array(16).keys()].map((i) => h("option", { value: i + 1, selected: val === i + 1 }, `FX ${i + 1} · ${fxName(i + 1)}`)));
}
function fxParams(slot) {
  if (!slot) return null;
  const key = slot + ":" + (S.fx[slot] || "");
  if (S.fxParams[key] === undefined) {
    S.fxParams[key] = null;
    api(`/api/fx/${slot}`).then((p) => { S.fxParams[key] = p; render(); }).catch(() => {});
  }
  return S.fxParams[key];
}
function fxParamSelect(st, enumsOnly) {
  const ps = fxParams(st.slot);
  if (!ps) return h("select", { disabled: true }, h("option", {}, "Loading…"));
  const list = ps.filter((p) => !p.readonly && p.type !== "str" && p.name !== "mdl" && (!enumsOnly || p.type === "enum" || p.type === "fenum"));
  const present = list.some((p) => p.name === st.param);
  return h("select", { onchange: (e) => { st.param = e.target.value; delete st.value; commit(); } },
    h("option", { value: "", selected: !st.param }, "Choose…"),
    st.param && !present && h("option", { value: st.param, selected: true }, `${st.param} (not in this model/mode)`),
    list.map((p) => h("option", { value: p.name, selected: p.name === st.param },
      `${p.longname}${p.unit ? " (" + p.unit + ")" : ""}${p.type === "enum" ? " ▾" : ""}`)));
}
function fxValueInput(st) {
  const p = (fxParams(st.slot) || []).find((x) => x.name === st.param);
  if (!p) return h("input", { type: "text", disabled: true, placeholder: "choose parameter" });
  if (p.type === "enum" || p.type === "fenum")
    return h("select", { onchange: (e) => { st.value = p.type === "fenum" ? +e.target.value : e.target.value; commit(false); } },
      h("option", { value: "" }, "Choose…"), p.items.map((it) => h("option", { value: it, selected: it === st.value }, it)));
  return h("span", {}, numInput(st.value, (v) => { st.value = v; }, { step: p.type === "int" ? 1 : "any", min: p.min, ph: `${+(+p.min).toFixed(2)}–${+(+p.max).toFixed(2)}` }),
    p.unit && h("span", { class: "unit" }, p.unit));
}

function targetBtn(t, set, chOnly) {
  const L = targetLabel(t);
  return h("button", { class: "target" + (t ? "" : " unset"), onclick: () => pickTarget(t, set, chOnly) },
    h("span", { class: "tc", style: L.col ? `background:${WCOL[L.col]}` : "" }, L.cap), h("span", { class: "tn" }, L.name));
}

// ---------------------------------------------------------------------------- target picker modal
function pickTarget(current, set, chOnly) {
  const cur = parseTarget(current);
  let tab = cur ? (cur.bus ? "send" : cur.kind) : "ch";
  let src = cur?.bus ? { kind: cur.kind, n: cur.n } : null;
  const m = $("modal");
  const close = () => { m.hidden = true; m.replaceChildren(); };
  const choose = (v) => { set(v); close(); };
  const grid = (kind, count, onPick, isOn) => h("div", { class: "strips" }, [...Array(count).keys()].map((i) => {
    const n = i + 1, s = stripInfo(kind, n);
    return h("button", { class: "strip" + (s.name ? "" : " blank") + (isOn(n) ? " on" : ""), onclick: () => onPick(n) },
      h("span", { class: "sc", style: s.col ? `background:${WCOL[s.col]}` : "" }, stripCap(kind, n)),
      h("span", { class: "sn" }, s.name || "—"));
  }));
  const draw = () => {
    const tabs = chOnly ? [["ch", "CH"]] : [...KINDS.map(([k, l]) => [k, l]), ["send", "SENDS"]];
    let body;
    if (tab === "send") {
      body = h("div", { class: "picksplit" },
        h("div", {}, h("p", { class: "muted" }, "1 · Source channel"),
          grid("ch", 40, (n) => { src = { kind: "ch", n }; draw(); }, (n) => src?.kind === "ch" && src.n === n),
          h("p", { class: "muted" }, "or aux"),
          grid("aux", 8, (n) => { src = { kind: "aux", n }; draw(); }, (n) => src?.kind === "aux" && src.n === n)),
        h("div", {}, h("p", { class: "muted" }, "2 · Destination bus"),
          src ? grid("bus", 16, (b) => choose(`${src.kind}/${src.n}/send/${b}`), (b) => cur?.bus === b && cur.n === src.n)
            : h("p", { class: "hint" }, "Choose a source first.")));
    } else {
      const [, , cnt] = KINDS.find((k) => k[0] === tab);
      body = grid(tab, cnt, (n) => choose(`${tab}/${n}`), (n) => cur && !cur.bus && cur.kind === tab && cur.n === n);
    }
    m.replaceChildren(h("div", { class: "dialog", onclick: (e) => e.stopPropagation() },
      h("div", { class: "phead" }, chOnly ? "SELECT CHANNEL" : "SELECT TARGET", h("div", { class: "right" }, h("button", { class: "btn sm", onclick: close }, "Close"))),
      h("div", { class: "tabs" }, tabs.map(([k, l]) => h("button", { class: tab === k ? "on" : "", onclick: () => { tab = k; draw(); } }, l))),
      h("div", { class: "pbody" }, !S.live?.wing.connected && h("p", { class: "hint" }, "WING not connected: names and colours unavailable."), body)));
  };
  m.onclick = close;
  draw(); m.hidden = false;
}

// ---------------------------------------------------------------------------- LED editor
function previewCss(val, hsv) { return hsvCss(hsv); }   // swatches now show the LED colour itself
function colourPicker(val, set, { allowNone = false, noneLabel = "Background" } = {}) {
  // Palette swatches + brightness. A palette colour at full brightness is stored by name,
  // anything else as [h, s, v] (v 0..200, the firmware's cap).
  const cur = colourOf(val);
  const isOff = val === "off" || (cur && cur[2] === 0);
  const named = !isOff && cur && Object.entries(PALETTE).find(([n, c]) => n !== "off" && c[0] === cur[0] && c[1] === cur[1]);
  const custom = cur && !isOff && !named;
  const bright = cur && !isOff ? cur[2] / 200 : 1;
  const store = (h0, s0, v) => { const n = Object.entries(PALETTE).find(([k, c]) => k !== "off" && c[0] === h0 && c[1] === s0); return n && v === 200 ? n[0] : [h0, s0, v]; };
  const wrap = h("div", {});
  wrap.append(h("div", { class: "swatches" },
    allowNone && h("button", { class: "sw none" + (val == null ? " on" : ""), title: noneLabel, onclick: () => { set(undefined); commit(); } }),
    SWATCHES.map(([n, c, rgb]) => h("button", { class: "sw" + ((n === "off" ? isOff : named && named[0] === n) ? " on" : ""), title: n,
      style: `background:${rgb}`,
      onclick: () => { set(n === "off" ? "off" : store(c[0], c[1], Math.round(200 * bright))); commit(); } })),
    h("button", { class: "btn sm" + (custom ? " amber" : ""), onclick: () => {
      if (custom) return;
      const b0 = cur && !isOff ? cur : [0, 255, 200];          // nudge saturation so it no longer matches a swatch
      set([b0[0], b0[1] >= 255 ? 254 : b0[1] + 1, b0[2]]); commit(); } }, "Custom")));
  if (cur && !isOff) {
    const prev = h("span", { class: "swprev", style: `background:${previewCss(val, cur)}` });
    const pct = h("span", {}, Math.round(bright * 100) + "%");
    const hsv = [...cur];
    const apply = () => { const v = custom ? [...hsv] : store(hsv[0], hsv[1], hsv[2]); set(v); prev.style.background = previewCss(v, hsv); commit(false); };
    const box = h("div", { class: "hsv" });
    if (custom) ["H", "S"].forEach((lbl, i) => {
      const out = h("span", {}, hsv[i]);
      box.append(h("span", {}, lbl), h("input", { type: "range", min: 0, max: 255, value: hsv[i],
        oninput: (e) => { hsv[i] = +e.target.value; out.textContent = hsv[i]; apply(); }, onchange: () => render() }), out);
    });
    box.append(h("span", {}, "☀"), h("input", { type: "range", min: 4, max: 200, value: hsv[2], title: "Brightness",
      oninput: (e) => { hsv[2] = +e.target.value; pct.textContent = Math.round(hsv[2] / 2) + "%"; apply(); }, onchange: () => render() }), pct);
    wrap.append(h("div", { class: "row", style: "align-items:center;gap:8px;margin-top:6px" }, prev, box));
  }
  return wrap;
}
// ---------------------------------------------------------------------------- macros page
function macroUsers(name) {
  const users = [];
  const uses = (d) => d === name || (d && d.toggle && d.toggle.includes(name));
  for (const [l, L] of Object.entries(S.cfg.layers || {})) {
    for (const [wm, b] of Object.entries(L.buttons || {})) if (uses(b.do)) users.push(`L${+l + 1} WM${wm}`);
    for (const [k, e] of Object.entries(L.encoders || {})) if (e.push && uses(e.push.do)) users.push(`L${+l + 1} ${k} push`);
  }
  return users;
}
function renameMacro(old, nu) {
  if (!nu || nu === old || S.cfg.macros[nu]) return false;
  const ms = {}; for (const [k, v] of Object.entries(S.cfg.macros)) ms[k === old ? nu : k] = v; S.cfg.macros = ms;
  const fix = (o, key) => { if (o[key] === old) o[key] = nu; else if (o[key]?.toggle) o[key].toggle = o[key].toggle.map((x) => (x === old ? nu : x)); };
  for (const L of Object.values(S.cfg.layers || {})) {
    for (const b of Object.values(L.buttons || {})) fix(b, "do");
    for (const e of Object.values(L.encoders || {})) if (e.push) fix(e.push, "do");
  }
  S.macroSel = nu; return true;
}
function renderMacros() {
  const names = macroNames();
  if (S.macroSel && !S.cfg.macros[S.macroSel]) S.macroSel = null;
  const list = h("table", { class: "grid" }, h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", {}, "Steps"), h("th", {}, "Used by"))),
    h("tbody", {}, names.map((n) => h("tr", { class: n === S.macroSel ? "sel" : "", onclick: () => { S.macroSel = n; render(); } },
      h("td", {}, n), h("td", {}, (S.cfg.macros[n].steps || []).length), h("td", { class: "muted" }, macroUsers(n).join(", ") || "—")))));
  let editor;
  const mc = S.macroSel && S.cfg.macros[S.macroSel];
  if (!mc) editor = h("div", { class: "editor-empty" }, names.length ? "Select a macro" : "No macros yet");
  else {
    const users = macroUsers(S.macroSel);
    const nameIn = h("input", { type: "text", value: S.macroSel, onchange: (e) => {
      if (!renameMacro(S.macroSel, e.target.value.trim())) e.target.value = S.macroSel; commit(); } });
    editor = [h("div", { class: "phead" }, S.macroSel.toUpperCase(), h("div", { class: "right" },
      h("button", { class: "btn sm danger", onclick: () => {
        if (users.length && !confirm(`"${S.macroSel}" is used by ${users.join(", ")}. Delete anyway? Those controls will stop working.`)) return;
        delete S.cfg.macros[S.macroSel]; S.macroSel = null; commit(); } }, "Delete"))),
    h("div", { class: "pbody" },
      sect("Name", nameIn),
      sect("If triggered while running", seg([["restart", "Restart"], ["ignore", "Ignore"], ["parallel", "Run again"]], mc.retrigger || "restart", (v) => { mc.retrigger = v; commit(); }, "sm")),
      sect("Steps", h("p", { class: "hint" }, "Run in order. Waits don't block other controls."), stepList(mc.steps ||= [], false)),
      sect("Used by", h("p", { class: "muted" }, users.join(", ") || "Not assigned to any control yet.")))];
  }
  return h("div", { class: "cols", style: "grid-template-columns:minmax(260px,380px) 1fr" },
    panel("MACROS", list, { right: h("button", { class: "btn sm light", onclick: () => { S.macroSel = newMacro(); commit(); } }, "+ New"), bodyCls: "scroll" }),
    h("section", { class: "panel" }, editor));
}

// ---------------------------------------------------------------------------- console page
async function scan() {
  S.scanning = true; render();
  S.consoles = await api("/api/scan").catch(() => []);
  S.scanning = false; render();
}
function renderConsole() {
  const L = S.live?.wing || {};
  const ipIn = h("input", { type: "text", value: S.cfg.console?.ip || "", placeholder: "e.g. 192.168.1.62", style: "flex:1;min-width:160px" });
  const connect = async (ip) => { await api("/api/console", { method: "POST", body: JSON.stringify({ ip }) }); S.cfg.console = { ...(S.cfg.console || {}), ip }; render(); };
  const table = h("table", { class: "grid" },
    h("thead", {}, h("tr", {}, ["No", "Model", "Name", "IP", "FW"].map((c) => h("th", {}, c)))),
    h("tbody", {}, (S.consoles || []).map((c, i) => h("tr", { class: c.ip === L.host ? "sel" : "", onclick: () => connect(c.ip) },
      h("td", {}, i + 1), h("td", {}, c.model), h("td", {}, c.name), h("td", {}, c.ip), h("td", {}, c.firmware.split("-")[0])))));
  const info = L.info || {};
  const fx = h("div", { class: "fxgrid" }, [...Array(16).keys()].map((i) => {
    const n = i + 1, md = S.fx[n];
    return h("div", { class: "fxcell" + (md && md !== "NONE" ? "" : " empty") }, h("b", {}, `FX${n}`), md && md !== "NONE" ? md : "—");
  }));
  return h("div", { class: "cols", style: "grid-template-columns:1fr 1fr;grid-auto-rows:min-content" },
    panel("SELECT CONSOLE", [h("p", { class: "hint", style: "margin-top:0" }, "Consoles found on this network. Click one to connect."),
      S.consoles == null ? h("p", { class: "muted" }, "Not scanned yet.") : S.consoles.length ? table : h("p", { class: "muted" }, "No consoles answered (broadcasts don't cross VLANs: use a manual IP).")],
    { right: h("button", { class: "btn sm light", disabled: S.scanning, onclick: scan }, S.scanning ? "Scanning…" : "Rescan") }),
    panel("CONNECTION", h("dl", { class: "kv" },
      h("dt", {}, "Status"), h("dd", {}, h("span", { class: "chip" }, h("i", { class: "dot" + (L.connected ? " on" : "") }), L.connected ? "Connected" : L.host ? "Connecting…" : "Searching")),
      h("dt", {}, "Address"), h("dd", {}, L.host || "auto-discover"),
      h("dt", {}, "Mode"), h("dd", {}, S.cfg.console?.ip ? "Manual IP" : "Auto (first console found)"))),
    panel("MANUAL IP ADDRESS", h("div", { class: "row" }, ipIn,
      h("button", { class: "btn light", onclick: () => connect(ipIn.value.trim()) }, "Connect"),
      h("button", { class: "btn ghost", onclick: () => connect("") }, "Auto"))),
    panel("CONSOLE INFORMATION", h("dl", { class: "kv" },
      ...[["Name", info.name], ["Model", info.model], ["Serial", info.serial], ["Firmware", info.firmware]].flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v || "—")]))),
    panel("EFFECTS LOADED", fx, { style: "grid-column:1/-1" }));
}

// ---------------------------------------------------------------------------- setup page
function renderSettings() {
  S.cfg.pad ||= {};
  const p = S.cfg.pad;
  const file = h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const cfg = JSON.parse(await f.text());
      const r = await api("/api/config", { method: "PUT", body: JSON.stringify(cfg) });
      if (!r.ok) throw new Error(r.error);
      S.cfg = cfg; S.sel = null; S.macroSel = null; alert("Config imported."); render();
    } catch (err) { alert("Import failed: " + err.message); }
    e.target.value = "";
  } });
  const raw = h("textarea", { class: "raw", spellcheck: "false" }, JSON.stringify(S.cfg, null, 2));
  const padFile = h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const r = await api("/api/pad/restore", { method: "POST", body: await f.text() });
      if (!r.ok) throw new Error(r.error);
      alert(`Restored: ${r.changed} change(s) written to the pad.${r.note ? "\n" + r.note : ""}`);
      S.vial = null; refreshMeta();
    } catch (err) { alert("Restore failed: " + err.message); }
    e.target.value = "";
  } });
  return h("div", { class: "cols", style: "grid-template-columns:1fr 1fr;grid-auto-rows:min-content" },
    panel("PAD", [
      sect("Background colour", h("p", { class: "hint" }, "Shown on every key without an active state. Default matches the case."),
        colourPicker(p.background, (v) => { p.background = v; }, { allowNone: true, noneLabel: "Case colour (default)" })),
      sect("Hold keys", h("div", { class: "row" },
        field("Default hold time", h("span", {}, numInput(p.hold_ms, (v) => { p.hold_ms = v; }, { ph: 800, step: 50, min: 100 }), h("span", { class: "unit" }, "ms"))),
        field("Default cancel window", h("span", {}, numInput(p.cancel_ms, (v) => { p.cancel_ms = v; }, { ph: 400, step: 50, min: 0 }), h("span", { class: "unit" }, "ms")))),
        h("p", { class: "hint" }, "Each key can override these.")),
    ]),
    panel("CONFIGURATION", [
      sect("Move between machines", h("p", { class: "hint" }, "Each machine keeps its own config. Export here and import on the other machine."),
        h("div", { class: "row" },
          h("button", { class: "btn light", onclick: () => {
            const a = h("a", { href: URL.createObjectURL(new Blob([JSON.stringify(S.cfg, null, 2)], { type: "application/json" })),
              download: `wingmacro-${new Date().toISOString().slice(0, 10)}.json` });
            a.click(); URL.revokeObjectURL(a.href);
          } }, "Export"),
          h("button", { class: "btn", onclick: () => file.click() }, "Import…"), file)),
      sect("Pad backup", h("p", { class: "hint" }, "Everything stored on the pad itself: keymap, knobs, key macros, tap dance, combos. Reflashing the firmware wipes these, so back up first and restore after."),
        h("div", { class: "row" },
          h("button", { class: "btn light", onclick: async () => {
            const r = await fetch("/api/pad/backup"); const b = await r.json();
            if (!r.ok) { alert("Backup failed: " + b.error); return; }
            const a = h("a", { href: URL.createObjectURL(new Blob([JSON.stringify(b, null, 1)], { type: "application/json" })),
              download: `kb16-pad-${new Date().toISOString().slice(0, 10)}.json` });
            a.click(); URL.revokeObjectURL(a.href);
          } }, "Back up pad"),
          h("button", { class: "btn", onclick: () => padFile.click() }, "Restore to pad…"), padFile)),
      sect("Advanced: raw config", h("p", { class: "hint" }, "Schema: docs/config-model.md"), raw,
        h("div", { class: "row", style: "margin-top:6px" }, h("button", { class: "btn", onclick: async () => {
          try {
            const cfg = JSON.parse(raw.value);
            const r = await api("/api/config", { method: "PUT", body: JSON.stringify(cfg) });
            if (!r.ok) throw new Error(r.error);
            S.cfg = cfg; render();
          } catch (err) { alert("Not applied: " + err.message); }
        } }, "Apply"))),
    ]));
}

// ---------------------------------------------------------------------------- keymap page (Vial replacement)
const KNOB_ENC = { left: 0, right: 1, big: 2 };
const KNOB_PUSH = { left: [0, 4], right: [1, 4], big: [2, 4] };
function rawKc(layer, row, col) { return S.km?.layers?.[layer]?.[row * (S.km.cols || 5) + col]; }
function effectiveKc(layer, row, col) {
  for (let l = layer; l >= 0; l--) { const kc = rawKc(l, row, col); if (kc == null) return null; if (kc !== 1) return kc; }
  return 0;
}
function rawEnc(layer, enc, cw) { return S.km?.encoders?.[layer]?.[enc]?.[cw ? 1 : 0]; }
function effectiveEnc(layer, enc, cw) {
  for (let l = layer; l >= 0; l--) { const kc = rawEnc(l, enc, cw); if (kc == null) return null; if (kc !== 1) return kc; }
  return 0;
}
function slotInfo(sel, slot) {                // -> {label, raw, eff, body}
  const L = S.layer;
  if (sel.kind === "key") {
    const row = Math.floor(sel.idx / 4), col = sel.idx % 4;
    return { label: `Key ${sel.idx + 1}`, raw: rawKc(L, row, col), eff: effectiveKc(L, row, col), body: { layer: L, row, col } };
  }
  if (slot === "push") {
    const [row, col] = KNOB_PUSH[sel.knob];
    return { label: "Push", raw: rawKc(L, row, col), eff: effectiveKc(L, row, col), body: { layer: L, row, col } };
  }
  const cw = slot === "cw", enc = KNOB_ENC[sel.knob];
  return { label: cw ? "Turn right" : "Turn left", raw: rawEnc(L, enc, cw), eff: effectiveEnc(L, enc, cw), body: { layer: L, encoder: enc, cw } };
}
async function setKc(info, kc) {
  S.kmErr = "";
  const r = await api("/api/keymap", { method: "POST", body: JSON.stringify({ ...info.body, kc }) }).catch((e) => ({ ok: false, error: String(e) }));
  if (!r.ok) S.kmErr = r.error;
  await refreshMeta();
  render();
}
function wmUsedOnLayer(layer) {
  const used = new Set();
  for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) { const kc = effectiveKc(layer, r, c); if (KC.isWM(kc)) used.add(kc); }
  for (let e = 0; e < 3; e++) for (const cw of [0, 1]) { const kc = effectiveEnc(layer, e, cw); if (KC.isWM(kc)) used.add(kc); }
  return used;
}

function renderKeymap() {
  const ok = S.km?.connected;
  const banks = h("div", { class: "banks" },
    [0, 1, 2, 3].map((l) => h("button", { class: "btn light" + (S.layer === l ? " on" : ""), onclick: () => pickLayer(l) }, `LAYER ${l + 1}`)),
    h("div", { class: "follow" }, h("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:6px" },
      toggleBtn("LINK TO PAD", S.follow, (v) => { S.follow = v; if (v && S.live) S.layer = S.live.pad.layer; render(); }),
      toggleBtn("SELECT ON PRESS", S.selectOnPress, (v) => { S.selectOnPress = v; render(); }))));
  const cap = (kc) => {
    if (kc == null) return h("span", { class: "nm" }, "?");
    return h("span", { class: "nm kmname" + (KC.isWM(kc) ? " wm" : "") }, KC.name(kc));
  };
  const keys = h("div", { class: "keys" }, [...Array(16).keys()].map((idx) => {
    const row = Math.floor(idx / 4), col = idx % 4, raw = rawKc(S.layer, row, col);
    return h("button", { class: "key km" + (S.kmSel?.kind === "key" && S.kmSel.idx === idx ? " sel" : "") + (raw === 1 ? " inherit" : ""),
      "data-idx": idx, onclick: () => { S.kmSel = { kind: "key", idx }; render(); } },
      cap(raw === 1 ? effectiveKc(S.layer, row, col) : raw), raw === 1 && h("span", { class: "act" }, "▽ from below"));
  }));
  const knob = (k) => {
    const enc = KNOB_ENC[k], [pr, pc] = KNOB_PUSH[k];
    const n = (kc) => (kc == null ? "?" : KC.name(kc));
    const el = h("button", { class: "knob kmknob" + (S.kmSel?.knob === k ? " sel" : ""), "data-knob": k,
      onclick: () => { S.kmSel = { kind: "knob", knob: k }; if (!["push", "ccw", "cw"].includes(S.kmSlot)) S.kmSlot = "push"; render(); } },
      dial(), h("span", { class: "kl" }, `${n(effectiveEnc(S.layer, enc, 0))} / ${n(effectiveEnc(S.layer, enc, 1))}`));
    return el;
  };
  const big = knob("big"); big.className += " big";
  const padBody = h("div", { class: "doio" }, h("div", { class: "well" }, keys), knob("left"), knob("right"), big);

  let editor;
  if (!ok) editor = h("div", { class: "editor-empty" }, "Pad not connected", h("br"), h("span", { class: "hint" }, "Plug the pad into this machine to edit its keymap."));
  else if (!S.kmSel) editor = h("div", { class: "editor-empty" }, "Select a key or knob", h("br"), h("span", { class: "hint" }, "or press a WM key on the pad"));
  else editor = kmEditor();
  return h("div", { class: "cols padpage" },
    h("section", { class: "panel" }, h("div", { class: "phead" }, "LAYERS"), banks),
    panel("KEYMAP", h("div", { class: "padwrap" }, padBody, h("div", { class: "legend" },
      h("span", {}, h("b", { style: "color:var(--amber)" }, "WM"), " keys are mapped on the Pad page"),
      h("span", {}, "▽ transparent: uses the layer below"),
      h("span", {}, "Changes save to the pad immediately")))),
    h("section", { class: "panel" }, editor));
}

function kmEditor() {
  const sel = S.kmSel;
  const slots = sel.kind === "key" ? [null] : ["push", "ccw", "cw"];
  const slot = sel.kind === "key" ? null : S.kmSlot;
  const info = slotInfo(sel, slot);
  const title = sel.kind === "key" ? `KEY ${sel.idx + 1}` : `${sel.knob === "big" ? "BIG" : sel.knob.toUpperCase()} KNOB`;
  const slotBtns = sel.kind === "knob" && h("div", { class: "row", style: "margin-bottom:12px" }, slots.map((s) => {
    const i = slotInfo(sel, s);
    return h("button", { class: "target" + (s === slot ? " on" : ""), onclick: () => { S.kmSlot = s; render(); } },
      h("span", { class: "tc" }, i.label.toUpperCase()), h("span", { class: "tn" }, KC.name(i.raw)));
  }));
  const cur = h("div", { class: "kmcur" }, h("span", { class: "big" + (KC.isWM(info.raw) ? " wm" : "") }, KC.name(info.raw)),
    info.raw === 1 && h("span", { class: "muted" }, `Transparent: uses ${KC.name(info.eff)} from a lower layer`),
    KC.isWM(info.raw) && h("span", { class: "muted" }, "WM key: what it does is set on the Pad page"),
    info.raw === 0 && h("span", { class: "muted" }, "Does nothing"));
  return [h("div", { class: "phead" }, `${title} · LAYER ${S.layer + 1}`),
    h("div", { class: "pbody" },
      slotBtns, cur,
      S.kmErr && h("p", { style: "color:var(--red)" }, S.kmErr),
      kcPicker(info.raw, (v) => setKc(info, v), { used: wmUsedOnLayer(S.layer), redraw: render }))];
}

// Keycode picker: tabs of keycodes, modifier combos, raw hex. Used inline and in a modal.
function kcPicker(current, onPick, { used = new Set(), redraw = render } = {}) {
  const tab = S.kmTab;
  if (["KEY MACROS", "TAP DANCE"].includes(tab) && !S.vial) loadVial();
  const group = KC.groups.find((g) => g[0] === tab) || KC.groups[0];
  const modable = (kc) => kc >= 0x04 && kc <= 0x73;
  const withMods = (kc) => (S.kmMods && modable(kc) ? (S.kmMods << 8) | kc : kc);
  const grid = h("div", { class: "kcgrid" }, group[1].map((kc) => {
    const v = withMods(kc);
    return h("button", { class: "kc" + (v === current ? " on" : "") + (KC.isWM(kc) ? " wmk" : "") + (KC.isWM(kc) && used.has(kc) ? " used" : ""),
      title: KC.isWM(kc) && used.has(kc) ? "Already used on this layer" : kcDetail(kc), onclick: () => onPick(v) }, KC.name(v));
  }));
  const modsRow = ["LETTERS", "F-KEYS", "EDIT / NAV", "NUMPAD"].includes(tab) && h("div", { class: "row", style: "margin-bottom:8px;gap:6px;align-items:center" },
    h("span", { class: "muted", style: "font-size:12px;text-transform:uppercase" }, "With"),
    KC.MODS.map(([b, n]) => h("button", { class: "btn sm" + (S.kmMods & b ? " amber" : ""), onclick: () => { S.kmMods ^= b; redraw(); } }, n)),
    h("button", { class: "btn sm" + (S.kmMods & 0x10 ? " amber" : ""), onclick: () => { S.kmMods ^= 0x10; redraw(); } }, "Right"));
  const hex = h("input", { type: "text", placeholder: "0x7E00", style: "width:90px" });
  return h("div", {},
    h("div", { class: "tabs kmtabs" }, KC.groups.map(([g]) => h("button", { class: g === tab ? "on" : "", onclick: () => { S.kmTab = g; redraw(); } }, g))),
    h("div", { style: "padding-top:10px" }, modsRow, grid),
    tab === "WINGMACRO" && h("p", { class: "hint" }, "Amber dot = already used on this layer. WM keys do nothing on their own: map them on the Pad page."),
    ["KEY MACROS", "TAP DANCE"].includes(tab) && h("div", { class: "row", style: "margin-top:10px;align-items:center" },
      h("span", { class: "hint" }, tab === "KEY MACROS" ? "Pick one to assign it. Its keystrokes are set in the macro editor." : "Pick one to assign it. Its actions are set in the tap dance editor."),
      h("button", { class: "btn sm light", onclick: () => {
        const m = $("modal"); m.hidden = true; m.replaceChildren();
        S.kmView = tab === "KEY MACROS" ? "macros" : "tapdance";
        S.vialSel = current >= 0x7700 && current < 0x7720 ? current - 0x7700 : current >= 0x5700 && current < 0x5720 ? current - 0x5700 : 0;
        render();
      } }, tab === "KEY MACROS" ? "Open macro editor" : "Open tap dance editor")),
    h("div", { class: "row", style: "margin-top:12px;align-items:center" }, h("span", { class: "muted", style: "font-size:12px;text-transform:uppercase" }, "Any keycode"), hex,
      h("button", { class: "btn sm", onclick: () => { const v = parseInt(hex.value, 16); if (!isNaN(v)) onPick(v); } }, "Set")));
}
function kcDetail(kc) {                      // contents of a key macro / tap dance, for tooltips
  if (kc >= 0x7700 && kc < 0x7720) return S.vial?.macros ? macroSummary(S.vial.macros[kc - 0x7700]) : "";
  if (kc >= 0x5700 && kc < 0x5720) {
    const t = S.vial?.tap_dance?.[kc - 0x5700];
    return t ? ["tap", "hold", "double_tap", "tap_hold"].filter((k) => t[k]).map((k) => `${k.replace("_", " ")}: ${KC.name(t[k])}`).join(", ") || "empty" : "";
  }
  return "";
}
function pickKeycode(current, onPick) {
  const m = $("modal");
  const close = () => { m.hidden = true; m.replaceChildren(); };
  const draw = () => m.replaceChildren(h("div", { class: "dialog", onclick: (e) => e.stopPropagation() },
    h("div", { class: "phead" }, "SELECT KEYCODE", h("div", { class: "right" },
      h("button", { class: "btn sm", onclick: () => { onPick(0); close(); } }, "Clear"), h("button", { class: "btn sm", onclick: close }, "Close"))),
    h("div", { class: "pbody" }, kcPicker(current, (v) => { onPick(v); close(); }, { redraw: draw }))));
  m.onclick = close; draw(); m.hidden = false;
}
function kcSlot(label, kc, onPick) {
  return field(label, h("button", { class: "target" + (kc ? "" : " unset"), onclick: () => pickKeycode(kc, onPick) },
    h("span", { class: "tn" + (KC.isWM(kc) ? " wm" : "") }, kc ? KC.name(kc) : "—")));
}

// ---------------------------------------------------------------------------- Vial extras: key macros, tap dance, combos
async function loadVial(reload) {
  S.vial = await api("/api/vial" + (reload ? "?reload=1" : "")).catch(() => ({ connected: false }));
  if (S.vial.connected && (!S.vialDraft || reload)) S.vialDraft = clone(S.vial.macros);
  render();
}
async function vialPost(kind, body) {
  S.kmErr = "";
  const r = await api("/api/vial/" + kind, { method: "POST", body: JSON.stringify(body) }).catch((e) => ({ ok: false, error: String(e) }));
  if (!r.ok) S.kmErr = r.error;
  return r.ok;
}
function lockChip() {
  const u = S.vial?.unlock || {};
  return h("div", { class: "row", style: "gap:6px;align-items:center" },
    h("span", { class: "chip" }, h("i", { class: "dot" + (u.unlocked ? " on" : "") }), u.unlocked ? "Unlocked" : "Locked"),
    u.unlocked ? h("button", { class: "btn sm", onclick: async () => { await vialPost("lock", {}); loadVial(); } }, "Lock")
      : h("button", { class: "btn sm light", onclick: startUnlock }, "Unlock…"));
}
async function startUnlock() {
  if (!(await vialPost("unlock", {}))) { render(); return; }
  const keys = (S.vial?.unlock?.keys || []).map(([r, c]) => (c < 4 && r < 4 ? `key ${r * 4 + c + 1}` : `row ${r} col ${c}`));
  const m = $("modal");
  const bar = h("div", { class: "progress" }, h("i"));
  const msg = h("p", {}, `Hold ${keys.join(" and ")} together until the bar fills (about 5 seconds).`);
  m.replaceChildren(h("div", { class: "dialog", style: "max-width:480px" }, h("div", { class: "phead" }, "UNLOCK PAD"),
    h("div", { class: "pbody" }, msg, bar, h("p", { class: "hint" }, "Vial requires this before keystroke macros can be changed. It stays unlocked until you lock it or unplug the pad."))));
  m.onclick = null; m.hidden = false;
  const t0 = Date.now();
  while (Date.now() - t0 < 32000) {
    await new Promise((r) => setTimeout(r, 150));
    const u = await api("/api/vial/unlock").catch(() => ({}));
    bar.firstChild.style.width = `${Math.round((1 - (u.counter ?? 50) / 50) * 100)}%`;
    if (u.unlocked) { msg.textContent = "Unlocked."; break; }
    if (!u.in_progress && Date.now() - t0 > 1000) { msg.textContent = "Unlock didn't complete. Try again."; break; }
  }
  setTimeout(() => { m.hidden = true; m.replaceChildren(); loadVial(); }, 700);
}

function macroSummary(actions) {
  if (!actions?.length) return "—";
  return actions.map((a) => a.text != null ? `"${a.text}"` : a.delay != null ? `${a.delay}ms`
    : Object.entries(a).map(([k, v]) => (k === "tap" ? "" : k + " ") + v.map(KC.name).join("+")).join("")).join(" · ");
}
function renderKeyMacros() {
  const v = S.vial, draft = S.vialDraft || [];
  const i = S.vialSel ?? 0, acts = draft[i] || [];
  const dirty = JSON.stringify(draft) !== JSON.stringify(v.macros);
  const list = h("table", { class: "grid" }, h("thead", {}, h("tr", {}, h("th", {}, "Macro"), h("th", {}, "Actions"))),
    h("tbody", {}, draft.map((m, n) => h("tr", { class: n === i ? "sel" : "", onclick: () => { S.vialSel = n; render(); } },
      h("td", { style: "white-space:nowrap" }, `M${n}`), h("td", { class: "muted" }, macroSummary(m))))));
  const row = (a, n) => {
    const kind = a.text != null ? "text" : a.delay != null ? "delay" : Object.keys(a)[0];
    let val;
    if (kind === "text") val = h("input", { type: "text", value: a.text, style: "flex:1;min-width:160px", oninput: (e) => { a.text = e.target.value; } , onchange: () => render() });
    else if (kind === "delay") val = h("span", {}, h("input", { type: "number", value: a.delay, min: 0, step: 10, oninput: (e) => { a.delay = +e.target.value || 0; } }), h("span", { class: "unit" }, "ms"));
    else val = h("div", { class: "row", style: "gap:4px" }, a[kind].map((kc, k) => h("button", { class: "target", onclick: () => pickKeycode(kc, (nv) => { if (nv) a[kind][k] = nv; else a[kind].splice(k, 1); render(); }) },
      h("span", { class: "tn" }, KC.name(kc)))), h("button", { class: "btn sm", onclick: () => pickKeycode(0, (nv) => { if (nv) { a[kind].push(nv); render(); } }) }, "+ Key"));
    return h("div", { class: "step" + (kind === "delay" ? " wait" : "") }, h("div", { class: "no" }, n + 1),
      h("div", {}, h("div", { class: "row", style: "align-items:center" },
        h("select", { onchange: (e) => { const k = e.target.value; acts[n] = k === "text" ? { text: "" } : k === "delay" ? { delay: 100 } : { [k]: kind === "text" || kind === "delay" ? [] : a[kind] }; render(); } },
          [["text", "Type text"], ["tap", "Tap keys"], ["down", "Press (down)"], ["up", "Release (up)"], ["delay", "Delay"]].map(([k, l]) => h("option", { value: k, selected: k === kind }, l))), val)),
      h("div", { class: "row", style: "gap:4px;flex-wrap:nowrap" },
        iconBtn("up", () => { if (n) { [acts[n - 1], acts[n]] = [acts[n], acts[n - 1]]; render(); } }, "Move up"),
        iconBtn("down", () => { if (n < acts.length - 1) { [acts[n + 1], acts[n]] = [acts[n], acts[n + 1]]; render(); } }, "Move down"),
        iconBtn("x", () => { acts.splice(n, 1); render(); }, "Remove")));
  };
  const unlocked = v.unlock?.unlocked;
  const editor = [h("div", { class: "phead" }, `KEY MACRO M${i}`),
    h("div", { class: "pbody" },
      h("p", { class: "hint", style: "margin-top:0" }, `Typed by the pad on the computer it's plugged into (e.g. Wing Edit shortcuts). Assign M${i} to a key on the Keymap tab.`),
      h("div", { class: "steps" }, acts.length ? acts.map(row) : h("div", { class: "hint" }, "Empty.")),
      h("div", { class: "addrow" }, [["text", "+ Text"], ["tap", "+ Tap keys"], ["down", "+ Press"], ["up", "+ Release"], ["delay", "+ Delay"]].map(([k, l]) =>
        h("button", { class: "btn sm", onclick: () => { (draft[i] ||= []).push(k === "text" ? { text: "" } : k === "delay" ? { delay: 100 } : { [k]: [] }); render(); } }, l))),
      h("div", { class: "row", style: "margin-top:16px;align-items:center" },
        h("button", { class: "btn amber", disabled: !dirty || !unlocked, onclick: async () => {
          if (await vialPost("macros", { macros: S.vialDraft })) await loadVial(true); else render(); } }, "Save to pad"),
        dirty && h("button", { class: "btn ghost", onclick: () => { S.vialDraft = clone(v.macros); render(); } }, "Discard changes"),
        dirty && h("span", { style: "color:var(--amber)" }, "Unsaved changes"),
        !unlocked && h("span", { class: "muted" }, "Unlock the pad to save macros.")),
      S.kmErr && h("p", { style: "color:var(--red)" }, S.kmErr))];
  return h("div", { class: "cols", style: "grid-template-columns:minmax(280px,420px) 1fr" },
    panel("KEY MACROS", list, { bodyCls: "scroll", right: h("span", { class: "muted", style: "font-size:12px" }, `${v.macro_used} / ${v.macro_size} bytes`) }),
    h("section", { class: "panel" }, editor));
}
function renderTapDance() {
  const v = S.vial, i = S.vialSel ?? 0;
  const td = v.tap_dance[i];
  const set = async (k, val) => { const nt = { ...td, [k]: val }; if (await vialPost("tap_dance", { idx: i, ...nt })) v.tap_dance[i] = nt; render(); };
  const sum = (t) => [t.tap, t.hold, t.double_tap, t.tap_hold].some(Boolean)
    ? [["tap", t.tap], ["hold", t.hold], ["2×", t.double_tap], ["tap+hold", t.tap_hold]].filter(([, k]) => k).map(([l, k]) => `${l} ${KC.name(k)}`).join(" · ") : "—";
  const list = h("table", { class: "grid" }, h("thead", {}, h("tr", {}, h("th", {}, "Entry"), h("th", {}, "Actions"))),
    h("tbody", {}, v.tap_dance.map((t, n) => h("tr", { class: n === i ? "sel" : "", onclick: () => { S.vialSel = n; render(); } },
      h("td", { style: "white-space:nowrap" }, `TD(${n})`), h("td", { class: "muted" }, sum(t))))));
  const editor = [h("div", { class: "phead" }, `TAP DANCE TD(${i})`), h("div", { class: "pbody" },
    h("p", { class: "hint", style: "margin-top:0" }, `One key, different keycodes for tap, hold, double tap and tap-then-hold. Assign TD(${i}) to a key on the Keymap tab. Saves to the pad immediately.`),
    h("div", { class: "row" }, kcSlot("On tap", td.tap, (k) => set("tap", k)), kcSlot("On hold", td.hold, (k) => set("hold", k)),
      kcSlot("On double tap", td.double_tap, (k) => set("double_tap", k)), kcSlot("On tap + hold", td.tap_hold, (k) => set("tap_hold", k))),
    h("div", { style: "height:12px" }),
    field("Tapping term", h("span", {}, h("input", { type: "number", value: td.term, min: 50, step: 10, onchange: (e) => set("term", +e.target.value || 200) }), h("span", { class: "unit" }, "ms"))),
    S.kmErr && h("p", { style: "color:var(--red)" }, S.kmErr))];
  return h("div", { class: "cols", style: "grid-template-columns:minmax(280px,420px) 1fr" }, panel("TAP DANCE", list, { bodyCls: "scroll" }), h("section", { class: "panel" }, editor));
}
function renderCombos() {
  const v = S.vial, i = S.vialSel ?? 0;
  const c = v.combos[i];
  const save = async (nc) => { if (await vialPost("combo", { idx: i, ...nc })) v.combos[i] = nc; render(); };
  const sum = (x) => x.output ? `${x.inputs.filter(Boolean).map(KC.name).join(" + ")} → ${KC.name(x.output)}` : "—";
  const list = h("table", { class: "grid" }, h("thead", {}, h("tr", {}, h("th", {}, "Combo"), h("th", {}, "Keys → result"))),
    h("tbody", {}, v.combos.map((x, n) => h("tr", { class: n === i ? "sel" : "", onclick: () => { S.vialSel = n; render(); } },
      h("td", {}, `${n}`), h("td", { class: "muted" }, sum(x))))));
  const editor = [h("div", { class: "phead" }, `COMBO ${i}`), h("div", { class: "pbody" },
    h("p", { class: "hint", style: "margin-top:0" }, "Press these keycodes together to send the result instead. Matches keycodes, not key positions. Saves to the pad immediately."),
    h("div", { class: "row" }, [0, 1, 2, 3].map((k) => kcSlot(`Key ${k + 1}`, c.inputs[k], (nv) => { const inp = [...c.inputs]; inp[k] = nv; save({ ...c, inputs: inp }); }))),
    h("div", { style: "height:12px" }),
    kcSlot("Result", c.output, (nv) => save({ ...c, output: nv })),
    S.kmErr && h("p", { style: "color:var(--red)" }, S.kmErr))];
  return h("div", { class: "cols", style: "grid-template-columns:minmax(280px,420px) 1fr" }, panel("COMBOS", list, { bodyCls: "scroll" }), h("section", { class: "panel" }, editor));
}
function renderKeymapPage() {
  const views = [["keymap", "Keymap"], ["macros", "Key macros"], ["tapdance", "Tap dance"], ["combos", "Combos"]];
  const view = S.kmView || "keymap";
  let body;
  if (view === "keymap") body = renderKeymap();
  else if (!S.vial) { loadVial(); body = h("div", { class: "editor-empty" }, "Reading the pad…"); }
  else if (!S.vial.connected) body = h("div", { class: "editor-empty" }, "Pad not connected");
  else body = { macros: renderKeyMacros, tapdance: renderTapDance, combos: renderCombos }[view]();
  return h("div", { class: "kmpage" },
    h("div", { class: "tabs pagetabs" }, views.map(([k, l]) => h("button", { class: view === k ? "on" : "", onclick: () => { S.kmView = k; S.vialSel = 0; S.kmErr = ""; render(); } }, l)),
      view !== "keymap" && S.vial?.connected && h("div", { class: "tabright" }, lockChip(), h("button", { class: "btn sm ghost", onclick: () => loadVial(true) }, "Re-read pad"))),
    body);
}

// ---------------------------------------------------------------------------- render / nav
function render() {
  const page = $("page");
  const keepScroll = [...page.querySelectorAll(".pbody")].map((e) => e.scrollTop);
  const pageScroll = page.scrollTop;
  page.replaceChildren(({ pad: renderPad, macros: renderMacros, console: renderConsole, settings: renderSettings, keymap: renderKeymapPage })[S.page]());
  page.querySelectorAll(".pbody").forEach((e, i) => { e.scrollTop = keepScroll[i] || 0; });
  page.scrollTop = pageScroll;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.page === S.page));
  renderTop();
  const cur = S.page === "pad" ? S.sel : S.page === "keymap" ? S.kmSel : null;
  const sel = cur ? `/${S.layer + 1}/${cur.kind === "key" ? cur.idx + 1 : cur.knob}` : "";
  history.replaceState(null, "", `#${S.page}${sel}`);
}
function fromHash() {                       // #pad/2/5 = layer 2, key 5; #pad/1/left; #macros
  const [pageView, layer, ctl] = location.hash.slice(1).split("/");
  const [page, view] = pageView.split(":");               // e.g. #keymap:tapdance
  if (view) S.kmView = view;
  if (["pad", "macros", "console", "settings", "keymap"].includes(page)) S.page = page;
  if (layer) S.layer = +layer - 1;          // Follow pad stays on; the live layer wins once known
  if (ctl) S.sel = /^\d+$/.test(ctl) ? { kind: "key", idx: +ctl - 1 } : { kind: "knob", knob: ctl };
  if (ctl && S.page === "keymap") { S.kmSel = S.sel; S.sel = null; }
}
function go(p) { S.page = p; if (p === "console" && S.consoles == null) scan(); render(); }
document.querySelectorAll("#nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.page)));
addEventListener("keydown", (e) => { if (e.key === "Escape") { const m = $("modal"); m.hidden = true; m.replaceChildren(); } });

function editing() {
  const a = document.activeElement;
  return a && ["INPUT", "TEXTAREA", "SELECT"].includes(a.tagName) || !$("modal").hidden;
}

// ---------------------------------------------------------------------------- live
function flash(sel) {
  const el = document.querySelector(sel); if (!el) return;
  el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 180);
}
function onLive(st) {
  const prevLayer = S.live?.pad.layer;
  S.live = st;
  if (S.follow && st.pad.connected && st.pad.layer !== S.layer) { S.layer = st.pad.layer; if (!editing()) render(); }
  const fxChanged = JSON.stringify(st.fx) !== JSON.stringify(Object.fromEntries(Object.entries(S.fx).filter(([, v]) => v && v !== "NONE")));
  if (fxChanged) refreshMeta();
  for (const ev of st.events || []) {
    if (ev.type !== "key") continue;
    const knob = ev.row >= 252 ? ["left", "right"][ev.col] : ev.col === 4 && ev.row < 2 ? ["left", "right"][ev.row] : null;
    if (S.page === "keymap" && ev.layer === S.layer && ev.pressed && S.selectOnPress && !editing()) {
      if (ev.row >= 252) { S.kmSel = { kind: "knob", knob: ["left", "right", "big"][ev.col] }; S.kmSlot = ev.row === 253 ? "cw" : "ccw"; }
      else if (ev.col === 4) { S.kmSel = { kind: "knob", knob: ["left", "right", "big"][ev.row] }; S.kmSlot = "push"; }
      else S.kmSel = { kind: "key", idx: ev.row * 4 + ev.col };
      render();
    }
    if (S.page === "pad" && ev.layer === S.layer) {
      if (ev.pressed && S.selectOnPress && !editing()) {
        const nsel = knob ? { kind: "knob", knob } : ev.row < 4 && ev.col < 4 ? { kind: "key", idx: ev.row * 4 + ev.col } : null;
        if (nsel && JSON.stringify(nsel) !== JSON.stringify(S.sel)) { S.sel = nsel; render(); }
      }
      flash(knob ? `[data-knob=${knob}]` : `[data-idx="${ev.row * 4 + ev.col}"]`);
    }
  }
  renderTop();
  if (S.page === "pad") {               // update LED bars in place
    const onL = st.pad.connected && st.pad.layer === S.layer;
    document.querySelectorAll(".key[data-idx]").forEach((k) => {
      const led = onL && st.leds ? st.leds[+k.dataset.idx] : null;
      if (led) k.style.setProperty("--led", hsvCss(led)); else k.style.removeProperty("--led");
    });
  }
  if (S.page === "console" && prevLayer !== undefined && !editing()) renderConsoleLive();
}
let lastConsoleState = "";
function renderConsoleLive() {
  const k = JSON.stringify(S.live.wing);
  if (k !== lastConsoleState) { lastConsoleState = k; render(); }
}
function connectWs() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`);
  ws.onmessage = (m) => onLive(JSON.parse(m.data));
  ws.onclose = () => { S.live = null; renderTop(); setTimeout(connectWs, 1500); };
}
async function refreshMeta() {
  const [strips, pad, fx, km] = await Promise.all([api("/api/strips"), api("/api/pad"), api("/api/fx"), api("/api/keymap")]).catch(() => []);
  if (!strips) return;
  const changed = JSON.stringify([strips, pad, fx, km]) !== JSON.stringify([S.strips, S.pad, S.fx, S.km]);
  S.strips = strips; S.pad = pad; S.fx = fx; S.km = km;
  if (changed && !editing()) render();
}

(async function init() {
  fromHash();
  S.cfg = await api("/api/config");
  for (const l of ["0", "1", "2", "3"]) S.cfg.layers[l] ||= { buttons: {}, encoders: {} };
  await refreshMeta();
  if (S.page === "console") scan();
  render();
  connectWs();
  setInterval(refreshMeta, 4000);
})();
