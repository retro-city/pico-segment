#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Test and beep tones for the piezo, in the panel's 8-bit mono format.

    tools/mktone.py beep  sounds/beep4k.wav   # POST-style beep, 4 kHz square
    tools/mktone.py sweep sounds/sweep.wav    # 0.5 -> 10 kHz glide, find resonance

beep: two short 4 kHz square-wave beeps at full scale. A square wave at
the sounder's resonance is exactly the datasheet SPL test signal, so
this is the loudest thing a 4 kHz piezo can make -- and it reads as a
PC POST beep. Cut at 16 kHz so 4 kHz is exact (2 samples up, 2 down)
and the PWM sits at 0 %/100 %: the disc sees a clean 6.6 V p-p square.

sweep: a slow full-scale sine glide from 0.5 to 10 kHz. Play it and
listen for the loud spot: that is your disc's resonance, and where a
tone should sit to be heard.
"""
import math
import sys
import wave


def write8(path, rate, vals):
    data = bytes(max(0, min(255, int(round(v * 127)) + 128)) for v in vals)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(data)
    print('%s: %d Hz, %.2f s, %d bytes' % (path, rate, len(data) / rate, len(data) + 44))


def beep(path, freq=4000, rate=16000, on=0.18, gap=0.09, count=2, ramp=0.004):
    per = rate // freq                     # samples per period; 4 at 16k/4k
    assert rate % freq == 0, 'pick a rate that is a multiple of the tone'
    vals = []
    for n in range(count):
        for i in range(int(on * rate)):
            v = 1.0 if (i % per) < per // 2 else -1.0
            # a few ms of ramp at each end so it starts and stops cleanly
            t = i / rate
            env = min(1.0, t / ramp, (on - t) / ramp)
            vals.append(v * env)
        if n < count - 1:
            vals += [0.0] * int(gap * rate)
    write8(path, rate, vals)


def sweep(path, f0=500.0, f1=10000.0, seconds=2.5, rate=32000):
    vals = []
    phase = 0.0
    n = int(seconds * rate)
    for i in range(n):
        t = i / rate
        f = f0 * (f1 / f0) ** (t / seconds)      # exponential glide
        phase += 2 * math.pi * f / rate
        vals.append(math.sin(phase))
    write8(path, rate, vals)


if __name__ == '__main__':
    kind, dst = sys.argv[1], sys.argv[2]
    {'beep': beep, 'sweep': sweep}[kind](dst)
