# Handoff: console scenes / snippets (2026-10-08)

Read CLAUDE.md first. App running in the container: `cd app && setsid nohup ../.venv/bin/python -m wingmacro --web-host 0.0.0.0 > <scratchpad>/app.log`
(find its PID with `ps -eo pid,args | awk '/python -m wingmacro --web-host/ && !/awk/'`; never `pkill -f`).
Pad is plugged into the container, firmware proto 4. Console: WING Rack "FRack" at 10.0.1.8.

## Done (2026-10-08)

FX model changes + knob ends: built, unit-tested, live-tested on empty slot 8 (TAP-DL rep -> ST-DL feed,
BODY -> "not in BODY"), UI checked in headless Chrome. See CLAUDE.md (FX) and `docs/config-model.md`.
Headless Chrome: `~/.cache/ms-playwright/chromium_headless_shell-1243/...` needs
`LD_LIBRARY_PATH=/tmp/claude-1001/-workspace-wingmacro/6ad255a2-b1de-4f08-8fc1-890b3b6be24c/scratchpad/libs/root/usr/lib/x86_64-linux-gnu`
(may be gone; then extract libatk etc. from .debs again).
Not checked: the pad OLED itself after a model change (unit test covers the label/"n/a").

## Next feature: console scenes / snippets

The user wants keys to fire the **console's own** show scenes/snippets (Wing Edit's local shows aren't reachable).
The console tree has a show-control node, so it looks possible:

- `/$ctl/lib/$action` enum `IDLE, GOPREV, GONEXT, GO, PREV, NEXT, GOTAG` (writable), with `/$ctl/lib/$actionidx`
  (int 0–16384) for the target index.
- `/$ctl/lib/$scenes` (ro enum: the show's scene/snip list, empty when read on 2026-10-07), `$active` ("ACTIVE
  SCENE/SNAP", str), `$actshow` ("ACTIVE SHOW"), `$activeid`, `$actidx` (ro).
- Not in the protocol PDF beyond the path names; behaviour (what GOTAG / NEXT vs GONEXT do, whether `$actionidx` is
  written first, snippets vs scenes) must be found by testing.

Plan: a `scene` key action: Go next / Go previous / Select next / Select previous / Go to <scene from the console's
list>. Picker reads `$scenes`. Pad screen shows the scene name after a recall (reuse `F0 06`).
**Safety: recalling a scene changes the whole mix.** Ask the user before any live test; ideally they load a test show
with harmless scenes first. Reading the `lib` nodes is safe.
