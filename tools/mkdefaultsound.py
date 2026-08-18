#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Wrap a WAV as a frozen Python module, so the firmware can seed the
drive with a default boot.wav on a freshly formatted filesystem.

    tools/mkdefaultsound.py sounds/spinup.wav defaultsound.py

The module holds the file verbatim as a bytes literal; frozen, that is
just the bytes in flash, no RAM until it is written out once.
"""
import sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    data = open(src, 'rb').read()
    with open(dst, 'w') as f:
        f.write('# SPDX-License-Identifier: GPL-3.0-only\n')
        f.write('# Copyright (C) 2026 Vidar Waagbø\n')
        f.write('"""Default boot sound, generated from %s by\n' % src)
        f.write('tools/mkdefaultsound.py -- do not edit. main.py writes it to\n')
        f.write('the drive as boot.wav on a freshly formatted filesystem."""\n\n')
        f.write('NAME = %r\n' % src.rsplit('/', 1)[-1])
        f.write('WAV = (\n')
        for i in range(0, len(data), 64):
            f.write('    %r\n' % data[i:i + 64])
        f.write(')\n')
    print('%s: %d bytes from %s' % (dst, len(data), src))


if __name__ == '__main__':
    main()
