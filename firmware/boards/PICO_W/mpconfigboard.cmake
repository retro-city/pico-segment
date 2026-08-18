# Pico Segment on a Raspberry Pi Pico W (see mpconfigboard.h). Same as
# the stock RPI_PICO_W board so the wireless stack still builds -- the
# panel does not use it, but a W without its cyw43 driver hangs at boot.
set(PICO_BOARD "pico_w")

set(MICROPY_PY_LWIP ON)
set(MICROPY_PY_NETWORK_CYW43 ON)

# Bluetooth
set(MICROPY_PY_BLUETOOTH ON)
set(MICROPY_BLUETOOTH_BTSTACK ON)
set(MICROPY_PY_BLUETOOTH_CYW43 ON)

# Freeze what the stock W board freezes; firmware/manifest.py picks this
# up via BOARD_DIR and adds the panel on top.
set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)
