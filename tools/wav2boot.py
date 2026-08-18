#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Turn any WAV into the boot.wav the panel plays fastest.

    tools/wav2boot.py in.wav boot.wav            # 16 kHz, 8-bit, mono
    tools/wav2boot.py in.wav boot.wav --rate 22050 --seconds 3 --gain 1.5

Output is mono, 8-bit unsigned PCM, at --rate (16 kHz default): the
device reads those bytes straight into its play buffer with no
conversion. Stereo is downmixed, other bit depths converted, other rates
resampled by linear interpolation (good enough for a piezo). --seconds
trims the length; --gain scales the level, clipping rather than wrapping.
Pure standard library, so it runs on the same apt Python as tools/mpr.
"""
import argparse
import struct
import sys
import wave


def read_wav(path):
    """-> (rate, [floats -1..1]) mono."""
    with wave.open(path, 'rb') as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), \
            w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        vals = [(b - 128) / 128.0 for b in raw]
    elif width == 2:
        vals = [v / 32768.0 for v in struct.unpack('<%dh' % (len(raw) // 2), raw)]
    elif width == 3:
        vals = [int.from_bytes(raw[i:i + 3], 'little', signed=True) / 8388608.0
                for i in range(0, len(raw), 3)]
    elif width == 4:
        vals = [v / 2147483648.0 for v in struct.unpack('<%di' % (len(raw) // 4), raw)]
    else:
        sys.exit('unsupported sample width %d' % width)
    if ch > 1:
        vals = [sum(vals[i:i + ch]) / ch for i in range(0, len(vals), ch)]
    return rate, vals


def resample(vals, src, dst):
    if src == dst:
        return vals
    n = int(len(vals) * dst / src)
    out = []
    step = src / dst
    for i in range(n):
        pos = i * step
        j = int(pos)
        frac = pos - j
        a = vals[j]
        b = vals[j + 1] if j + 1 < len(vals) else a
        out.append(a + (b - a) * frac)
    return out


def write_wav8(path, rate, vals):
    data = bytes(max(0, min(255, int(round(v * 127.0)) + 128)) for v in vals)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--rate', type=int, default=16000)
    ap.add_argument('--seconds', type=float, default=None,
                    help='trim to this length')
    ap.add_argument('--gain', type=float, default=1.0)
    args = ap.parse_args()

    rate, vals = read_wav(args.src)
    vals = resample(vals, rate, args.rate)
    if args.seconds is not None:
        vals = vals[:int(args.seconds * args.rate)]
    if args.gain != 1.0:
        vals = [max(-1.0, min(1.0, v * args.gain)) for v in vals]
    n = write_wav8(args.dst, args.rate, vals)
    print('%s: %d Hz 8-bit mono, %d samples = %.2f s, %d bytes'
          % (args.dst, args.rate, n, n / args.rate, n + 44))


if __name__ == '__main__':
    main()
