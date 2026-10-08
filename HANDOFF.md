# Handoff: FX model changes and knob ends (2026-10-08)

Read CLAUDE.md first. App running in the container: `cd app && setsid nohup ../.venv/bin/python -m wingmacro --web-host 0.0.0.0 > <scratchpad>/app.log`
(find its PID with `ps -eo pid,args | awk '/python -m wingmacro --web-host/ && !/awk/'`; never `pkill -f`).
Pad is plugged into the container, firmware proto 4. Console: WING Rack "FRack" at 10.0.1.8.

## Bugs reported by the user

1. **Changing the FX model in a slot breaks mappings.** FX4 went from Ultratap to the WING delay
   (`TAP-DL`?). The right knob is mapped to `/fx/4/rep` ("Repeats"), push-turn to `/fx/4/fact`.
   The WING delay has no `rep`; its equivalent is `feed` ("Feed", linf %, 0–100). The knob silently does nothing
   until the user deletes and re-adds the mapping. Want: changing the mounted FX shouldn't break controls where an
   equivalent exists.
2. **Factor wraps round** at the end of its list on a knob (`fact`: 1/4 … 1). Knob option lists currently wrap by
   design (`_param_step(wrap=None)`: enums wrap, numbers clamp). The user expects it to stop at the ends.

## Current design (relevant code)

- `actions.py` `_param_step` / `a_param` / `a_param_set`; `Context.param_def` / `node_defs` cache per node,
  dropped in `main.py` when a `.../mdl` change event arrives (`ctx.invalidate`).
- Steps store `path` and `plabel` only (the picker's label). No model, no longname, no role.
- `/api/params?path=/fx/N` returns the console's 0xdd defs (name, longname, type, unit, min/max, items).
- Config is versioned (`config.py`, now v5); changes to stored steps need a migration if the shape changes.

## Decisions (user, 2026-10-08)

- Auto-matching to the equivalent param in the new model: **yes, when sensible** (e.g. Ultratap Repeats ↔ WING
  delay Feed). The user's intuition: a console control/CC assigned to feedback on one delay model would land on
  repeats on another. **Check that idea in the survey**: the console may address FX params by position
  (`NodeDef.idx`); if equivalent params share an index across related models, use that as a matching signal
  (after same key, alongside the alias table), but confirm on real data before trusting it.
- Knob option lists **stop at the ends by default**; per-step **Wrap** toggle to turn wrapping on.

## Proposed fix

1. **Store what was picked**: on save, the picker records `model` (e.g. `TAP-DL`), the param key and its console
   longname/unit/type with the step (e.g. `pref: {model, key, longname, unit, type}`).
2. **Resolve at run time**: if `path`'s param doesn't exist in the slot's current model (or the model differs from
   `pref.model`), find the equivalent in the new model, in this order:
   same key → alias table (roles, e.g. feedback = `feed`/`rep`/`fb`…, time, factor/subdivision, pre-delay, decay,
   size, damping, lo/hi cut, mix) → same longname → nothing. Never guess across types/units badly (a % param must
   not drive an enum).
   Build the alias table from real data: dump the defs of every FX model (see test 1) into
   `docs/wing-fx-models-3.1.1.json` and group equivalent keys by role.
3. **No match**: do nothing, log once, and show "— n/a" on the pad screen (label + "n/a") so the user sees why.
   The UI shows the mapping as unavailable in the current model (greyed, with the model it was made for).
4. **Ends**: knob option lists stop at the ends by default (same as numbers). Add a per-step "Wrap" toggle
   (FX-slot-style button, like the tap Flash button) for anyone who wants wrapping. Keys' Increase/Decrease keep
   their existing stop/wrap choice.

## Tests

Live-console safety: only use **empty FX slots** (currently 5–8, 10–16 are NONE) for model changes, and put each
slot back to NONE afterwards. Don't touch slots 1–4 and 9 (in use) except reading. CH 40 is the test channel.

1. **Model survey (read + empty slot only)**: for each FX model in `/fx/N/mdl`'s item list, set an empty slot to it,
   read `0xdd` defs, save to `docs/wing-fx-models-3.1.1.json`, restore NONE. Use it to build and check the alias table.
2. **Unit tests (pytest, no hardware)**:
   - resolve: Ultratap `rep` → WING delay `feed`; `time` → `time`; `fact` → `fact`; reverb `dcy` across
     HALL/ROOM/PLATE/CHAMBER; pre-delay across reverbs; unknown → None.
   - type safety: never map to a param of an incompatible type/unit.
   - knob on an enum stops at the last/first option by default; wraps with `wrap: true`.
   - key Increase/Decrease unchanged (stop / wrap per step).
   - migration: existing steps without `pref` still work (resolved from `plabel`/key) and gain `pref` on next save.
   - `mdl` change event drops the cache and the next turn uses the new model's params.
3. **Live (empty slot, e.g. FX 8)**: map a test knob step to `/fx/8/<feedback>` on Ultratap, turn (via
   `/api/test/steps` with `ticks`), check it moves; switch slot 8 to the WING delay, turn again, check `feed`
   moves; switch to a reverb, check "n/a" and no write. Restore slot 8 to NONE and remove the test mapping.
4. **Pad screen**: after a model change the label shows the new param's name; at an end of `fact` the value stays
   at "1" (or "1/4") instead of wrapping.
5. **UI** (headless Chrome, `scratchpad/cdp.py` from the old session may be gone; recreate if needed): the
   mapping shows the param it resolves to now, and a clear "not in this model" state.

Commit after each step; update CLAUDE.md (FX section) and `docs/config-model.md` with the outcome.
