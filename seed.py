# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Give a fresh filesystem its files, so the USB drive is never bare.

Called from boot.py, which MicroPython runs BEFORE it brings USB up.
That matters twice over: flash writes disable interrupts in ~50 ms
bursts, which would stall the device mid-enumeration if a host were
already talking to it (Linux then gives the port up entirely), and it
guarantees the files exist before any host can mount the drive and
cache a view without them.

settings.json is (re)created whenever it is missing, with config.py's
defaults. The default boot.wav is only written when BOTH files are
missing -- a freshly formatted flash, or a deliberate delete-everything
reset -- so deleting just boot.wav still silences the panel, and
deleting just settings.json still resets the settings and nothing else.
"""

import json

import config

SETTINGS = 'settings.json'


def _exists(path):
    try:
        with open(path, 'rb'):
            return True
    except OSError:
        return False


def seed():
    fresh = not _exists(SETTINGS)
    if fresh:
        with open(SETTINGS, 'w') as f:
            f.write(json.dumps({'turbo': config.TURBO_ON_AT_BOOT,
                                'mhz_turbo': config.MHZ_TURBO,
                                'mhz_normal': config.MHZ_NORMAL,
                                'clicker': True}))
    if (fresh and config.BOOT_SOUND and config.BOOT_SOUND_SEED_DEFAULT
            and not _exists(config.BOOT_SOUND)):
        try:
            import defaultsound
        except ImportError:
            return                      # this image carries no default
        with open(config.BOOT_SOUND, 'wb') as f:
            f.write(defaultsound.WAV)
