# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""User-adjustable settings, persisted in settings.json on the drive.

config.py supplies the defaults and the hardware facts (pins,
polarities); everything a user might want to change without a rebuild
lives here, in a table, and the whole table is written to settings.json
so the file itself shows what can be set. Values are validated on the
way in, so a hand-edited file cannot put the panel in a bad state.

The USB-drive images expose the filesystem to the PC as mass storage,
raw flash sectors with no locking, so two parties keep their own idea
of the FAT. Rule: while a host is attached the PC owns the drive; the
panel keeps its changes in RAM and settles up when the host goes.
"""

import json
from machine import mem32

import config

# --- host presence -----------------------------------------------------

_SIE_STATUS = 0x50110050   # RP2040 USB controller status register


def usb_host_present():
    """True while a USB host has the panel enumerated and awake.

    Read off the USB controller rather than VBUS: on this board VBUS is
    also the power input, so it is high whenever the panel is on. With
    no host the bus idles and the SUSPENDED bit sets within 3 ms; a
    host that keeps us enumerated sends a frame every millisecond.
    """
    v = mem32[_SIE_STATUS]
    return bool(v & (1 << 16)) and not (v & (1 << 4))   # CONNECTED, !SUSPENDED


def refresh_fs():
    """Drop FatFs' cached view of the flash after the host has had it.

    Only on a FAT filesystem (the USB-drive images); a LittleFS build
    has no host to share with and is left alone.
    """
    try:
        import vfs
        import rp2
        fs = vfs.VfsFat(rp2.Flash())   # raises if the flash is not FAT
    except Exception:
        return
    vfs.umount('/')
    vfs.mount(fs, '/')


# --- the table -----------------------------------------------------------

MHZ_MAX = 9990


def _mhz(v):
    return min(MHZ_MAX, max(1, int(v)))


def _mhz_or_none(v):
    return None if v is None else _mhz(v)


def _int(lo, hi):
    return lambda v: min(hi, max(lo, int(v)))


def _int_list(lo, hi):
    def f(v):
        out = [min(hi, max(lo, int(x))) for x in v]
        if not out:
            raise ValueError('empty list')
        return out
    return f


def _text(v):
    return str(v)


def _text_or_none(v):
    return None if v in (None, '') else str(v)


# (key, default, validator). Order is the order in the file.
FIELDS = (
    ('turbo',          lambda: config.TURBO_ON_AT_BOOT,   bool),
    ('mhz_turbo',      lambda: config.MHZ_TURBO,          _mhz),
    ('mhz_normal',     lambda: config.MHZ_NORMAL,         _mhz_or_none),
    ('brightness',     lambda: config.BRIGHTNESS,         _int(0, 15)),
    ('spin_animation', lambda: config.SPIN_ANIMATION,     bool),
    ('clicker',        lambda: True,                      bool),
    ('click_hold_ms',  lambda: list(config.CLICK_HOLD_MS), _int_list(1, 500)),
    ('click_gap_ms',   lambda: config.CLICK_GAP_MS,       _int(10, 5000)),
    ('hdd_min_on_ms',  lambda: config.HDD_MIN_ON_MS,      _int(10, 5000)),
    ('boot_sound',     lambda: config.BOOT_SOUND,         _text_or_none),
    ('egg_text',       lambda: config.EGG_TEXT,           _text),
)


def dumps(values):
    """settings.json text: one key per line, so it is pleasant to edit."""
    lines = ['{']
    for i, (key, _, _) in enumerate(FIELDS):
        sep = ',' if i < len(FIELDS) - 1 else ''
        lines.append('  "%s": %s%s' % (key, json.dumps(values[key]), sep))
    lines.append('}')
    return '\n'.join(lines) + '\n'


def defaults():
    return {key: default() for key, default, _ in FIELDS}


class Settings:
    """The live settings, as attributes named after the table's keys.

    Reads and writes settings.json, deferring writes while a USB host
    owns the drive: save() then just marks the state dirty, and sync()
    -- called when the host goes away -- either adopts a file the host
    edited or writes the deferred state out. The file wins a conflict;
    someone went to the trouble of editing it.
    """

    PATH = 'settings.json'

    def __init__(self):
        self.dirty = False
        self._raw = None      # file content as last read/written
        self._defaults()
        self._load()

    def _defaults(self):
        for key, default, _ in FIELDS:
            setattr(self, key, default())

    def _load(self):
        try:
            with open(self.PATH, 'rb') as f:
                raw = f.read()
            d = json.loads(raw)
        except (OSError, ValueError):
            return  # missing or corrupt file -> what we had
        if not isinstance(d, dict):
            return
        for key, _, valid in FIELDS:
            if key in d:
                try:
                    setattr(self, key, valid(d[key]))
                except (ValueError, TypeError):
                    pass  # one bad value does not spoil the rest
        self._raw = raw

    def values(self):
        return {key: getattr(self, key) for key, _, _ in FIELDS}

    def save(self):
        """Write now, or defer if the PC owns the drive. True if written."""
        if usb_host_present():
            self.dirty = True
            return False
        raw = dumps(self.values())
        try:
            with open(self.PATH, 'w') as f:
                f.write(raw)
        except OSError:
            return False  # keep running even if the flash write fails
        self._raw = raw.encode()
        self.dirty = False
        return True

    def sync(self):
        """The host has gone: settle up. True if the file changed us."""
        refresh_fs()
        try:
            with open(self.PATH, 'rb') as f:
                raw = f.read()
        except OSError:
            raw = None
        if raw is not None and raw != self._raw:
            self._defaults()   # a pared-down file means "back to defaults"
            self._load()
            self.dirty = False
            return True
        if self.dirty:
            self.save()
        return False
