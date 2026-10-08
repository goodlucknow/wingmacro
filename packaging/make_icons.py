"""Write build/icon.png and build/icon.ico from the tray icon drawing (run before PyInstaller)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from wingmacro.tray import icon_image  # noqa: E402

out = Path(__file__).parent / "build"
out.mkdir(exist_ok=True)
icon_image(1024).save(out / "icon.png")
icon_image(256).save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icons in", out)
