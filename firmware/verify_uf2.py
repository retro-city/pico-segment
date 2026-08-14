#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Sanity-check built UF2 images before they go out as release assets.

Checks the container (block magics, RP2040 family, contiguous flash from
0x10000000) and that the frozen panel code actually made it in -- a
manifest that silently stopped freezing would otherwise produce a
perfectly valid image that boots to a bare REPL.

    firmware/verify_uf2.py out/*.uf2
"""
import struct
import sys

BLOCK = 512
MAGIC0 = 0x0A324655
MAGIC1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FAMILY_RP2040 = 0xE48BFF56
FLASH_BASE = 0x10000000

# Names that only exist if the project modules were frozen in. Keep them
# long enough to be specific: a stock MicroPython image happens to
# contain 'LOC', so the display text itself is no evidence.
MARKERS = (b'ht16k33_seg', b'settings.json', b'HT16K33 not found',
           b'LOCK_TEXT', b'lock_engaged', b'hdd_active')


def blocks(data):
    for off in range(0, len(data), BLOCK):
        b = data[off:off + BLOCK]
        magic0, magic1, _flags, addr, size, _seq, _total, family = \
            struct.unpack('<8I', b[:32])
        magic_end = struct.unpack('<I', b[-4:])[0]
        yield magic0, magic1, addr, size, family, magic_end, b[32:32 + size]


def check(path):
    data = open(path, 'rb').read()
    errors = []

    if not data or len(data) % BLOCK:
        return ['%d bytes is not a whole number of 512-byte UF2 blocks'
                % len(data)]

    payload = []
    expect_addr = FLASH_BASE
    for i, (m0, m1, addr, size, family, mend, chunk) in enumerate(blocks(data)):
        if (m0, m1, mend) != (MAGIC0, MAGIC1, MAGIC_END):
            errors.append('block %d: bad magic' % i)
            break
        if family != FAMILY_RP2040:
            errors.append('block %d: family %08x, expected rp2040 %08x'
                          % (i, family, FAMILY_RP2040))
            break
        if addr != expect_addr:
            errors.append('block %d: address %08x breaks the run (expected %08x)'
                          % (i, addr, expect_addr))
            break
        expect_addr = addr + size
        payload.append(chunk)

    if errors:
        return errors

    blob = b''.join(payload)
    missing = [m.decode() for m in MARKERS if m not in blob]
    if missing:
        errors.append('frozen code missing, no %s in the image'
                      % ', '.join(repr(m) for m in missing))

    if not errors:
        print('%s: ok, %d blocks, %d KiB at %08x..%08x'
              % (path, len(data) // BLOCK, (expect_addr - FLASH_BASE) // 1024,
                 FLASH_BASE, expect_addr))
    return errors


def main(paths):
    if not paths:
        print('usage: verify_uf2.py <image.uf2> ...', file=sys.stderr)
        return 2
    bad = 0
    for path in paths:
        for err in check(path):
            print('%s: %s' % (path, err), file=sys.stderr)
            bad = 1
    return bad


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
