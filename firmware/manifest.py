# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
#
# Freezes the front panel into a custom MicroPython image, so a board
# is set up by flashing one .uf2 with no files to copy afterwards.
# Build it with firmware/build.sh, which wraps:
#
#   make -C <micropython>/ports/rp2 BOARD=RPI_PICO_W \
#        FROZEN_MANIFEST=<repo>/firmware/manifest.py
#
# Frozen modules are read-only and sit in flash next to the filesystem,
# which still holds the writable settings.json. sys.path is
# ['', '.frozen'], so a config.py copied onto the board still shadows
# the frozen one -- handy for changing MHz or pin polarity without a
# rebuild. main.py is the exception: the boot code looks for a frozen
# main.py before the filesystem one, so changing it does need a rebuild
# (or an FS boot.py that imports something else).

# Keep whatever the board normally freezes. RPI_PICO_W has its own
# manifest (networking + aioble on top of the port's); plain RPI_PICO
# has none, so fall back to the port default it would have used. A
# missing include() raises ManifestFileError, which is not importable
# here, so test for the file rather than catching it. makemanifest.py
# is called with "-v BOARD_DIR=<path>" among its arguments.
import os
import sys

_board_dir = next((a.split("=", 1)[1] for a in sys.argv
                   if a.startswith("BOARD_DIR=")), None)

if _board_dir and os.path.isfile(os.path.join(_board_dir, "manifest.py")):
    include("$(BOARD_DIR)/manifest.py")
else:
    include("$(PORT_DIR)/boards/manifest.py")

freeze("..", (
    "boot.py",
    "seed.py",
    "main.py",
    "config.py",
    "ht16k33_seg.py",
    "bootsound.py",
    "defaultsound.py",
    "hddprobe.py",
    "segtest.py",
))
