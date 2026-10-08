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

## Desktop app (Windows, macOS)

Download from the repo's GitHub **Releases** page: `wingmacro-…-windows-setup.exe`, or
`wingmacro-…-macos-arm64.dmg` (Apple silicon) / `-macos-intel.dmg`.

- **Windows**: run the installer (no admin needed). Tick "Start wingmacro when I log in" if wanted.
  SmartScreen may warn about an unknown publisher: More info → Run anyway.
- **macOS**: open the dmg, drag wingmacro to Applications. The app isn't signed, so the first launch
  is blocked: System Settings → Privacy & Security → "Open Anyway" (once).

It runs in the background with a tray / menu-bar icon: **Open wingmacro** (the UI in a borderless Chrome app
window, else Edge, else your default browser; http://127.0.0.1:8780/), the console and pad status, **Start at login**, **Quit**. The icon's key is
amber while the console is connected. The first launch opens the UI; launching it again while it runs
just opens the UI. Log: `wingmacro.log` next to the config.

From source: `pip install -e '.[tray]'` then `python -m wingmacro tray`.

### Building

Push a tag (`git tag v0.1.0 && git push origin v0.1.0`) and `.github/workflows/release.yml` builds
the installer and disk images on GitHub and attaches them to a release; a tag with a dash
(`v0.2.0-beta1`) makes a pre-release. Locally: `pip install -e '.[tray,build]'`,
`python packaging/make_icons.py`, `pyinstaller packaging/wingmacro.spec`, then on Windows
`iscc /DVersion=X packaging\windows\wingmacro.iss` (Inno Setup 6).
