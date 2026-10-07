# Firmware: DOIO KB16 rev2 (Vial)

Keymap source lives in `vial/` and is symlinked into a separate
[vial-qmk](https://github.com/vial-kb/vial-qmk) checkout as `keymaps/wingmacro`.

## One-time setup

```sh
# toolchain (Ubuntu): gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi dfu-util python3-venv
git clone --depth 1 --filter=blob:none --sparse https://github.com/vial-kb/vial-qmk.git
cd vial-qmk
git sparse-checkout set --no-cone '/*' '!/keyboards/*' '/keyboards/doio/'
git submodule update --init --depth 1 --recursive lib/chibios lib/chibios-contrib lib/printf lib/lvgl
python3 -m venv ../.venv-qmk && ../.venv-qmk/bin/pip install -r requirements.txt qmk
```

## Build / flash

```sh
source ../.venv-qmk/bin/activate
firmware/build.sh          # build only
firmware/build.sh flash    # build, wait for bootloader, flash with dfu-util
```

Bootloader is stm32duino (USB `1eaf:0003`). It ignores dfu-util's detach, so `build.sh flash` ends with a USB reset to start the new firmware. Enter it with the reset button on the
back, by holding the top-left key while plugging in (this also clears EEPROM), or a
`QK_BOOT` key.

After the first flash, clear EEPROM (bootmagic) so the solid/dim default replaces
the stock rainbow stored in EEPROM.

## Notes

- Lighting is RGB_MATRIX + VialRGB; direct mode (per-LED host control) is on by default.
- `MIDI_ADVANCED` gives the full MIDI keycode set in the Vial editor.
- Big knob = mouse wheel on every layer. Everything else sends MIDI; see `docs/pad-map.md`.
