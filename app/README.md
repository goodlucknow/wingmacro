# wingmacro app

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m wingmacro discover          # find consoles (UDP WING? on 2222)
.venv/bin/python -m wingmacro fx 1              # list FX slot 1's parameters from the console
.venv/bin/python -m wingmacro --web-host 0.0.0.0  # run; web UI on :8780
.venv/bin/python -m pytest                      # unit tests, no hardware needed
```

Config: `~/.config/wingmacro/wingmacro.json` (Linux), `~/Library/Application Support/wingmacro/`
(macOS), `%APPDATA%\wingmacro\` (Windows); override with `--config`. Schema: `docs/config-model.md`.
Don't run the Vial editor against the pad while the app is running.
