#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Synthesize a drive spin-up boot sound sized for the piezo.

    tools/mkspinup.py sounds/spinup.wav

A motor whine that rises and settles (~1.6 s), a few seek ticks as the
heads load, then a short settle. Everything sits between 1.2 and 4 kHz
because that is where a piezo disc actually moves air. Written as
16 kHz 8-bit mono, i.e. already in the panel's fast-path format.
"""
import math
import random
import sys
import wave

RATE = 16000


def env(t, a, d, s, r, dur):
    """Simple attack/decay/sustain/release, t in seconds."""
    if t < a:
        return t / a
    if t < a + d:
        return 1 - (1 - s) * (t - a) / d
    if t < dur - r:
        return s
    return max(0.0, s * (dur - t) / r)


def spinup(seconds=1.6):
    out = []
    phase = 0.0
    n = int(seconds * RATE)
    for i in range(n):
        t = i / RATE
        # Pitch rises like a motor coming up to speed, then holds.
        f = 1200 + 2300 * (1 - math.exp(-t * 2.2))
        phase += 2 * math.pi * f / RATE
        # Two partials plus a bit of flutter so it is not a sine.
        v = (math.sin(phase) * 0.7 + math.sin(2 * phase + 0.4) * 0.3)
        v *= 1 + 0.15 * math.sin(2 * math.pi * 47 * t)
        out.append(v * env(t, 0.15, 0.4, 0.55, 0.4, seconds))
    return out


def tick(vals, at, strength=1.0):
    """A seek: a sharp broadband tick that rings down over ~8 ms."""
    start = int(at * RATE)
    for k in range(int(0.008 * RATE)):
        t = k / RATE
        v = (random.uniform(-1, 1) * 0.6 + math.sin(2 * math.pi * 3400 * t) * 0.4)
        v *= math.exp(-t * 400) * strength
        if start + k < len(vals):
            vals[start + k] += v


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else 'sounds/spinup.wav'
    random.seed(1911)
    vals = spinup()
    vals += [0.0] * int(0.9 * RATE)          # room for the seeks
    for at, s in ((1.75, 1.0), (1.79, 0.8), (1.95, 1.0), (2.02, 0.7), (2.25, 0.9)):
        tick(vals, at, s)
    peak = max(abs(v) for v in vals) or 1.0
    vals = [v / peak * 0.95 for v in vals]
    data = bytes(int(round(v * 127)) + 128 for v in vals)
    with wave.open(dst, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(RATE)
        w.writeframes(data)
    print('%s: %.2f s, %d bytes' % (dst, len(data) / RATE, len(data) + 44))


if __name__ == '__main__':
    main()
