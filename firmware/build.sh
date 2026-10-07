#!/usr/bin/env bash
# Build (and optionally flash) the wingmacro Vial keymap.
# Usage: firmware/build.sh [flash]
# Needs a vial-qmk checkout (default ../vial-qmk) set up per firmware/README.md.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
QMK_DIR="${QMK_DIR:-$here/../../vial-qmk}"
ln -sfn "$here/vial" "$QMK_DIR/keyboards/doio/kb16/rev2/keymaps/wingmacro"
cd "$QMK_DIR"
make doio/kb16/rev2:wingmacro
if [[ "${1:-}" == flash ]]; then
    echo "Waiting for bootloader (1eaf:0003) - press the reset button on the back..."
    until dfu-util -l 2>/dev/null | grep -q 1eaf:0003; do sleep 0.5; done
    dfu-util -a 2 -d 1eaf:0003 -R -D doio_kb16_rev2_wingmacro.bin
fi
