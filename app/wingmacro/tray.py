"""Desktop mode: the app in the background with a tray / menu-bar icon (Open UI, status, start at
login, Quit). Used by the Windows and macOS builds; `python -m wingmacro tray` from source.

The tray icon has to own the main thread (macOS requires it), so the app's asyncio loop runs in
a second thread. Without a desktop (no pystray, no display) it just runs headless.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

log = logging.getLogger(__name__)
NAME = "wingmacro"
MAC_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.wingmacro.plist"
LINUX_AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "wingmacro.desktop"
WIN_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


# --- start at login -----------------------------------------------------------

def launch_command():
    """How to start the app in tray mode: the packaged executable, or this Python."""
    exe = os.path.abspath(sys.executable)
    return [exe] if getattr(sys, "frozen", False) else [exe, "-m", "wingmacro", "tray"]


def autostart_enabled():
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN) as k:
                winreg.QueryValueEx(k, NAME)
            return True
        return (MAC_AGENT if sys.platform == "darwin" else LINUX_AUTOSTART).exists()
    except OSError:
        return False


def set_autostart(on):
    cmd = launch_command()
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return
    path = MAC_AGENT if sys.platform == "darwin" else LINUX_AUTOSTART
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        import plistlib
        path.write_bytes(plistlib.dumps({"Label": "com.wingmacro", "ProgramArguments": cmd,
                                         "RunAtLoad": True, "ProcessType": "Interactive"}))
    else:
        path.write_text("[Desktop Entry]\nType=Application\nName=wingmacro\n"
                        f"Exec={subprocess.list2cmdline(cmd)}\nX-GNOME-Autostart-enabled=true\n")


# --- icon -----------------------------------------------------------------------

def icon_image(size=64, lit=True):
    """The app icon: a dark key pad with one amber key (grey when the console isn't connected)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=(28, 28, 31, 255))
    pad, gap = size * 0.16, size * 0.05
    key = (size - 2 * pad - 3 * gap) / 4
    for i in range(16):
        y, x = divmod(i, 4)
        x0, y0 = pad + x * (key + gap), pad + y * (key + gap)
        on = i == 5
        fill = ((245, 166, 35, 255) if lit else (150, 150, 150, 255)) if on else (78, 78, 84, 255)
        d.rounded_rectangle((x0, y0, x0 + key, y0 + key), radius=max(1, key / 5), fill=fill)
    return im


# --- running ----------------------------------------------------------------------

def _get_status(url):
    try:
        with urllib.request.urlopen(url + "api/status", timeout=1) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def setup_logging(cfg_path, verbose):
    """Windowed builds have no console: log to a file next to the config as well."""
    log_path = Path(cfg_path).with_name("wingmacro.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stderr:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return log_path


def run(cfg_path, wing_ip, use_pad, web_host, web_port):
    ui_host = "127.0.0.1" if web_host in ("0.0.0.0", "::", "") else web_host
    url = f"http://{ui_host}:{web_port}/"
    if _get_status(url) is not None:  # already running: just show it
        webbrowser.open(url)
        return
    first_run = not Path(cfg_path).exists()

    from .main import App
    loop = asyncio.new_event_loop()
    stop = asyncio.Event()
    app = App(cfg_path, wing_ip, use_pad)
    started = threading.Event()
    failed = []

    def ready():
        started.set()
        if first_run:
            webbrowser.open(url)

    def serve():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(app.run(web_host, web_port, stop=stop, ready=ready))
        except Exception as e:
            log.exception("app stopped")
            failed.append(e)
            started.set()

    worker = threading.Thread(target=serve, name="wingmacro", daemon=True)
    worker.start()
    started.wait(30)

    try:
        import pystray
    except Exception as e:  # no desktop (or no pystray): keep running without an icon
        log.info("no tray icon (%s); UI at %s", e, url)
        try:
            worker.join()
        except KeyboardInterrupt:
            loop.call_soon_threadsafe(stop.set)
            worker.join(10)
        return

    def status_text(_item=None):
        if failed:
            return f"Stopped: {failed[0]}"
        w = "connected" if app.wing.connected else "not connected"
        p = "connected" if app.pad and app.pad.connected else "not connected"
        return f"Console {w} · pad {p}"

    def quit_(icon, _item=None):
        loop.call_soon_threadsafe(stop.set)
        worker.join(10)  # lets the pad go back to its own lighting
        icon.stop()

    def toggle_autostart(_icon, _item):
        try:
            set_autostart(not autostart_enabled())
        except OSError as e:
            log.warning("start at login: %s", e)

    icon = pystray.Icon(NAME, icon_image(64), "wingmacro", menu=pystray.Menu(
        pystray.MenuItem("Open wingmacro", lambda: webbrowser.open(url), default=True),
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start at login", toggle_autostart, checked=lambda _i: autostart_enabled()),
        pystray.MenuItem("Quit", quit_),
    ))

    def watch(icon):
        """Keep the status line and the icon's colour current."""
        icon.visible = True
        shown = None
        while worker.is_alive():
            now = (bool(app.wing.connected), bool(app.pad and app.pad.connected))
            if now != shown:
                if not shown or now[0] != shown[0]:
                    icon.icon = icon_image(64, now[0])
                shown = now
                icon.update_menu()
            worker.join(2)
        icon.update_menu()

    icon.run(setup=watch)
