# PyInstaller spec for the Windows and macOS apps: pyinstaller packaging/wingmacro.spec
# (run packaging/make_icons.py first). Version from WINGMACRO_VERSION, e.g. 0.1.0.
import os
import sys

HERE = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(HERE)
VERSION = os.environ.get("WINGMACRO_VERSION", "0.0.0")
ICON = os.path.join(HERE, "build", "icon.ico" if sys.platform == "win32" else "icon.png")
backend = {"win32": "pystray._win32", "darwin": "pystray._darwin"}.get(sys.platform, "pystray._xorg")

a = Analysis(
    [os.path.join(HERE, "launch.py")],
    pathex=[os.path.join(ROOT, "app")],
    datas=[(os.path.join(ROOT, "app", "wingmacro", "static"), "wingmacro/static")],
    hiddenimports=["hid", backend, "PIL.Image", "PIL.ImageDraw"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="wingmacro", console=False, icon=ICON,
          argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="wingmacro")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="wingmacro.app", icon=ICON, bundle_identifier="com.wingmacro",
                 version=VERSION, info_plist={
                     "LSUIElement": True,  # menu-bar app: no Dock icon
                     "CFBundleShortVersionString": VERSION,
                     "NSHumanReadableCopyright": "wingmacro",
                 })
