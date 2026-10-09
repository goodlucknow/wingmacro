# Handoff (2026-10-09): in practical use, waiting for user feedback

Read CLAUDE.md first. No active feature. The user runs **v0.1.0-beta4** on the Mac (main host, next to the desk)
and will report back after using it in practice. Start the next session from their report.

## State

- Releases: `v0.1.0-beta1..4` (pre-releases, GitHub Actions `release.yml` builds Windows setup.exe + macOS
  arm64/Intel dmgs on a `v*` tag in ~3 min). `gh` is authenticated in the container (`gh run watch`, `gh release view`).
  The user OKs each tag; pushing a tag may need their approval in the permission prompt.
- Mac beta4 tested by the user: runs, Quit works. Not yet tested: Windows build on the Surface (SmartScreen,
  firewall prompt, AHK alongside), Mac Local Network prompt / start at login on a fresh install, sleep/wake reconnect.
- Container: an app instance may still be running (`ps -eo pid,args | awk '/python -m wingmacro --web-host/ && !/awk/'`;
  never `pkill -f`). Start: `cd app && setsid nohup ../.venv/bin/python -m wingmacro --web-host 0.0.0.0 > <scratchpad>/app.log`.
  The pad is currently on the Mac, not the container. Console: WING Rack "FRack" at 10.0.1.8.
- Live-console safety: model changes only on **empty FX slots** (5–8, 10–16 were NONE; restore NONE after).
  CH 40 is the test channel.

## Done 2026-10-08 (see CLAUDE.md / docs/config-model.md)

- FX model changes: mappings follow to the equivalent param (key → role alias → long name → position → "n/a");
  `pref` stamped on save/connect; UI "now: X (made on MODEL)". Survey: `docs/wing-fx-models-3.1.1.json`
  (`tools/fx_survey.py`).
- Param hashes are per model: `Wing.forget(node)` on `mdl` change and on refresh (fixed Factor knob doing nothing).
- linf params are quantized to their `steps` grid: knob ticks move at least one grid step.
- Knob option lists stop at the ends; per-step Wrap.
- Tap tempo: pad screen + UI warn for slots without a ms `time` (OILCAN, BBD-DL). Measuring their knob→ms
  curve was offered and declined.
- Set level / Fade: Change by ±dB (`rel`) and Back (momentary boost: On +6 rel, Off Back).
- Desktop: UI opens in a borderless Chrome `--app` window (Edge/Chromium/default browser fallback).
- Quit: non-blocking on the Mac menu bar, web server `shutdown_timeout=1`, `os._exit` after shutdown.

## Tools

- `tools/ui_shot.py`: headless-Chrome screenshot of the UI with a temporary test macro (restores config).
  Needs `~/.cache/ms-playwright/chromium_headless_shell-1243/...` plus libatk etc. on `LD_LIBRARY_PATH`
  (an old scratchpad had them extracted under `.../scratchpad/libs/root/usr/lib/x86_64-linux-gnu`; may be gone,
  then extract from the .debs again).
- Live tests: drive steps through `POST /api/test/steps` (`{"steps": [{..., "ticks": n}]}`) and read back with a
  second `Wing` client (24 clients allowed).

## Open (none started)

- Linux systemd unit (`platform/linux/`), lowest packaging priority.
- AHK improvements (scope to Wing Edit window, runtime screen size).
- Parked: console scenes/snippets via `/$ctl/lib` (user, 2026-10-08: only if needed in practice; Wing Edit may
  cover it). Known nodes: `/$ctl/lib/$action` enum `IDLE, GOPREV, GONEXT, GO, PREV, NEXT, GOTAG` (writable),
  `$actionidx` (int 0–16384), `$scenes` (ro list), `$active`, `$actshow`, `$activeid`, `$actidx`. Behaviour must
  be found by testing; recalling a scene changes the whole mix, so ask the user before any live test.
