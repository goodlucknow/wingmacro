"use strict";
// wingmacro UI: pad view + mapping editor, macros, console connection, setup.
// Config schema: docs/config-model.md. Every edit autosaves (debounced) to /api/config.

// ---------------------------------------------------------------------------- state
const S = {
  cfg: null, strips: null, pad: null, fx: {}, fxParams: {}, live: null,
  page: "pad", layer: 0, follow: true, selectOnPress: true,
  sel: null,            // {kind:"key", idx} | {kind:"knob", knob}
  macroSel: null, consoles: null, scanning: false,
};
// WING strip colours 1..18 (approximate; to be checked against the console)
const WCOL = [null, "#6f8fb8", "#2f6fe0", "#3d3fd0", "#14b9cc", "#1fbf3c", "#8db31b", "#e3cf12", "#f08a1c",
  "#e5243b", "#f26a5e", "#ee3bd0", "#9a4fe0", "#8f979f", "#79c9f2", "#7fe39d", "#f2e07a", "#f6ae6c", "#f58fb3"];
const PALETTE = { red: [0, 255, 200], orange: [16, 255, 200], amber: [24, 255, 200], yellow: [43, 255, 200],
  green: [85, 255, 200], cyan: [128, 255, 200], blue: [170, 255, 200], purple: [191, 255, 200],
  magenta: [213, 255, 200], white: [0, 0, 200], off: [0, 0, 0] };
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
      onclick: () => { S.layer = l; S.follow = false; render(); },
    }, `LAYER ${l + 1}`)),
    h("div", { class: "follow" },
      h("div", { class: "row", style: "flex-direction:column;align-items:stretch;gap:6px" },
        toggleBtn("FOLLOW PAD", S.follow, (v) => { S.follow = v; if (v && live) S.layer = live.pad.layer; render(); }),
        toggleBtn("SELECT ON PRESS", S.selectOnPress, (v) => { S.selectOnPress = v; render(); }))));

  const keys = h("div", { class: "keys" }, [...Array(16).keys()].map((idx) => {
    const wm = wmAt(S.layer, idx);
    if (!wm) return h("div", { class: "key nowm", "data-idx": idx, title: "Not a WM key in Vial (ordinary key)" },
      h("span", { class: "nm" }, "Vial key"), h("span", { class: "act" }, "not WM"));
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
        seg([["press", "Press"], ["hold", "Hold"]], m.trigger || "press", (v) => { m.trigger = v; commit(); }),
        m.trigger === "hold" && field("Hold time", h("span", {}, numInput(m.hold_ms, (v) => { m.hold_ms = v; }, { ph: pad.hold_ms ?? 800, step: 50, min: 100 }), h("span", { class: "unit" }, "ms"))),
        m.trigger === "hold" && field("Cancel window", h("span", {}, numInput(m.cancel_ms, (v) => { m.cancel_ms = v; }, { ph: pad.cancel_ms ?? 400, step: 50, min: 0 }), h("span", { class: "unit" }, "ms")))),
      h("p", { class: "hint" }, m.trigger === "hold"
        ? "Hold until the key lights fully, then release. It flashes while armed; tap it again within the cancel window to cancel."
        : "Fires when the key is released.")),
    sect("Action", doEditor(() => m.do, (v) => { m.do = v; }, wm)),
    sect("LED", ledEditor(m)));
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
function doEditor(get, set, key) {
  const v = get();
  const mode = typeof v === "string" ? "macro" : v && v.toggle ? "toggle" : "steps";
  const modeSeg = seg([["steps", "Actions"], ["macro", "Macro"], ["toggle", "Toggle A/B"]], mode, (nv) => {
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
function colourPicker(val, set, { allowNone = false, noneLabel = "Background" } = {}) {
  const cur = colourOf(val);
  const custom = val && typeof val !== "string" && !Object.values(PALETTE).some((p) => sameCol(p, val));
  const wrap = h("div", {});
  const sw = h("div", { class: "swatches" },
    allowNone && h("button", { class: "sw none" + (val == null ? " on" : ""), title: noneLabel, onclick: () => { set(undefined); commit(); } }),
    Object.entries(PALETTE).map(([n, c]) => h("button", { class: "sw" + (val === n ? " on" : ""), title: n,
      style: `background:${n === "off" ? "#000" : hsvCss(c)}`, onclick: () => { set(n); commit(); } })),
    h("button", { class: "btn sm" + (custom ? " amber" : ""), onclick: () => { set([...(cur || [0, 255, 200])]); commit(); } }, "Custom"));
  wrap.append(sw);
  if (custom) {
    const box = h("div", { class: "hsv" });
    const prev = h("div", { style: `grid-column:1/-1;height:16px;border-radius:2px;background:${hsvCss(val)}` });
    ["H", "S", "V"].forEach((lbl, i) => {
      const out = h("span", {}, val[i]);
      box.append(h("span", {}, lbl), h("input", { type: "range", min: 0, max: i === 2 ? 200 : 255, value: val[i],
        oninput: (e) => { val[i] = +e.target.value; out.textContent = val[i]; prev.style.background = hsvCss(val); commit(false); } }), out);
    });
    box.append(prev); wrap.append(box);
  }
  return wrap;
}
function autoRuleText(m) {
  const st = firstSteps(m.do)[0];
  if (!st) return "No automatic LED for this action: the key shows the background colour.";
  const t = st.target && targetLabel(st.target).name;
  return { mute: `Red while ${t} is muted.`, softmute: `Red while ${t} is faded out; pulsing amber while fading.`,
    mgrp: `Red while mute group ${st.n} is on.`, tap: "Flashes on this key's tapped tempo." }[st.do]
    || "No automatic LED for this action: the key shows the background colour.";
}
const BINDS = [["mute", "Mute on"], ["softmute", "Soft mute (faded out)"], ["mgrp", "Mute group on"], ["floor", "Level at −∞"], ["fx", "FX value equals"], ["connected", "WING connected"]];
function ledEditor(m) {
  const r = m.led ?? "auto";
  const mode = r === "auto" ? "auto" : r === "none" ? "none" : "custom";
  const out = [h("div", { style: "margin-bottom:8px" }, seg([["auto", "Auto"], ["custom", "Custom"], ["none", "Off"]], mode, (v) => {
    m.led = v === "custom" ? { bind: "mute:" + (firstSteps(m.do)[0]?.target || "ch/1"), on: "red" } : v; commit();
  }, "sm"))];
  if (mode === "auto") out.push(h("p", { class: "hint" }, autoRuleText(m)));
  if (mode === "none") out.push(h("p", { class: "hint" }, "The key always shows its background colour."));
  if (mode === "custom") {
    const [kind, arg = ""] = r.bind.split(/:(.*)/s);
    const setBind = (k, a) => { r.bind = a != null && a !== "" ? `${k}:${a}` : k; commit(); };
    let argEl = null;
    if (["mute", "softmute", "floor"].includes(kind)) argEl = field("Target", targetBtn(arg, (v) => setBind(kind, v)));
    if (kind === "mgrp") argEl = field("Group", h("select", { onchange: (e) => setBind(kind, e.target.value) },
      [1, 2, 3, 4, 5, 6, 7, 8].map((n) => h("option", { value: n, selected: +arg === n }, n))));
    if (kind === "fx") {
      const [path = "", want = ""] = arg.split("==");
      const [slot, param] = path.split("/");
      const tmp = { slot: +slot || 1, param, value: want };
      argEl = h("div", { class: "row" },
        field("FX slot", fxSlotSelect(tmp.slot, (v) => setBind("fx", `${v}/==`))),
        field("Parameter", (() => { const s = fxParamSelect(tmp, false); s.onchange = (e) => setBind("fx", `${tmp.slot}/${e.target.value}==`); return s; })()),
        field("Equals", h("input", { type: "text", value: want, oninput: (e) => { r.bind = `fx:${tmp.slot}/${tmp.param || ""}==${e.target.value}`; commit(false); } })));
    }
    out.push(h("div", { class: "row", style: "margin-bottom:10px" },
      field("Lit when", h("select", { onchange: (e) => setBind(e.target.value, ["connected"].includes(e.target.value) ? null : e.target.value === "mgrp" ? "1" : firstSteps(m.do)[0]?.target || "ch/1") },
        BINDS.map(([k, l]) => h("option", { value: k, selected: k === kind }, l)))), argEl));
    out.push(field("On colour", colourPicker(r.on, (v) => { r.on = v; })));
    out.push(h("div", { style: "height:8px" }), field("Off colour", colourPicker(r.off, (v) => { r.off = v; }, { allowNone: true })));
    if (kind === "softmute") out.push(h("div", { style: "height:8px" }), field("While fading (pulses)", colourPicker(r.fading, (v) => { r.fading = v; }, { allowNone: true, noneLabel: "Amber (default)" })));
  }
  out.push(h("div", { style: "height:10px" }), field("Key background", colourPicker(m.background, (v) => { m.background = v; }, { allowNone: true, noneLabel: "Pad default" })));
  return h("div", {}, out);
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

// ---------------------------------------------------------------------------- render / nav
function render() {
  const page = $("page");
  const keepScroll = [...page.querySelectorAll(".pbody")].map((e) => e.scrollTop);
  const pageScroll = page.scrollTop;
  page.replaceChildren(({ pad: renderPad, macros: renderMacros, console: renderConsole, settings: renderSettings })[S.page]());
  page.querySelectorAll(".pbody").forEach((e, i) => { e.scrollTop = keepScroll[i] || 0; });
  page.scrollTop = pageScroll;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.page === S.page));
  renderTop();
  const sel = S.page === "pad" && S.sel ? `/${S.layer + 1}/${S.sel.kind === "key" ? S.sel.idx + 1 : S.sel.knob}` : "";
  history.replaceState(null, "", `#${S.page}${sel}`);
}
function fromHash() {                       // #pad/2/5 = layer 2, key 5; #pad/1/left; #macros
  const [page, layer, ctl] = location.hash.slice(1).split("/");
  if (["pad", "macros", "console", "settings"].includes(page)) S.page = page;
  if (layer) { S.layer = +layer - 1; S.follow = false; }
  if (ctl) S.sel = /^\d+$/.test(ctl) ? { kind: "key", idx: +ctl - 1 } : { kind: "knob", knob: ctl };
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
  const [strips, pad, fx] = await Promise.all([api("/api/strips"), api("/api/pad"), api("/api/fx")]).catch(() => []);
  if (!strips) return;
  const changed = JSON.stringify([strips, pad, fx]) !== JSON.stringify([S.strips, S.pad, S.fx]);
  S.strips = strips; S.pad = pad; S.fx = fx;
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
