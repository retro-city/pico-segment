#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
#
# Build a MicroPython image with the front panel frozen in, and drop the
# result in out/. Flash it by holding BOOTSEL while plugging the Pico W
# in, then copying the .uf2 onto the RPI-RP2 drive.
#
# Needs a MicroPython source tree with the rp2 submodules fetched and
# mpy-cross built; point MPY_DIR at it (default ../micropython):
#
#   git clone --depth 1 --branch v1.28.0 \
#       https://github.com/micropython/micropython.git
#   make -C micropython/mpy-cross
#   make -C micropython/ports/rp2 BOARD=RPI_PICO_W submodules
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MPY_DIR="${MPY_DIR:-$(dirname "$REPO")/micropython}"
BOARD="${BOARD:-RPI_PICO_W}"
OUT="$REPO/out"

if [ ! -d "$MPY_DIR/ports/rp2" ]; then
    echo "no MicroPython tree at $MPY_DIR (set MPY_DIR)" >&2
    exit 1
fi

make -C "$MPY_DIR/ports/rp2" \
    BOARD="$BOARD" \
    FROZEN_MANIFEST="$REPO/firmware/manifest.py" \
    -j"$(nproc)"

mkdir -p "$OUT"
# MPY_VERSION names the file; derive it from the tree unless told, so a
# CI checkout without tags still produces a predictable asset name.
VERSION="${MPY_VERSION:-$(git -C "$MPY_DIR" describe --tags --always 2>/dev/null || echo unknown)}"
NAME="segment1911-$BOARD-$VERSION.uf2"
cp "$MPY_DIR/ports/rp2/build-$BOARD/firmware.uf2" "$OUT/$NAME"

echo
echo "built $OUT/$NAME"
ls -l "$OUT"
