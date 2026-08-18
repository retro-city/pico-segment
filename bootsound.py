# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Play a WAV file through the piezo at power-on.

The piezo hangs between two GPIOs (the HDD clicker's pins). Two PIO
state machines run an 8-bit PWM at ~163 kHz on them, one inverted, so
the disc sees the difference and swings the full 6.6 V; DMA feeds each
machine one sample per tick of a DMA pacing timer set to the WAV's rate.
Nothing runs in Python while it plays, so it can overlap the lamp test.

    snd = bootsound.play('boot.wav', 96 * 1024, 22, 26)
    ...                      # do other things
    snd.wait()               # block until the last sample
    snd.stop()               # release PIO/DMA, hand the pins back

Accepts mono PCM WAV, 8-bit unsigned or 16-bit signed, 2-48 kHz.
8-bit is the fast path: its samples ARE the PWM values, so the file is
read straight into the play buffer. 16-bit is converted in a Python loop
(about a second per 50k samples on an RP2040), so convert on the host
with tools/wav2boot.py instead where you can. Stereo is refused rather
than mixed. Anything unplayable is reported and skipped; the panel must
never fail to boot over a sound file.
"""

import gc
import struct
import time

import rp2
from machine import Pin, freq, mem32

# One-shot 8-bit PWM. Y counts the period down; the pin goes high the
# moment Y meets the sample in X and stays high to the end, so duty is
# proportional to the sample. Both loop paths are three cycles, giving
# 3 * 256 + 3 = 771 cycles a period: ~162 kHz at 125 MHz. pull(noblock)
# keeps the last sample when the FIFO is empty, so DMA only has to
# deliver one byte per sample period and the machine repeats it.
# out(x, 8) rather than mov(x, osr): DMA byte writes may reach the FIFO
# replicated across all four lanes, and shifting right takes just the
# low byte either way.


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _pwm_pos():
    pull(noblock)           .side(0)
    out(x, 8)
    mov(y, isr)             # ISR holds the period, loaded once at start
    label("loop")
    jmp(x_not_y, "noset")
    jmp("skip")             .side(1)
    label("noset")
    nop()
    label("skip")
    jmp(y_dec, "loop")


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_HIGH, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _pwm_neg():
    pull(noblock)           .side(1)
    out(x, 8)
    mov(y, isr)
    label("loop")
    jmp(x_not_y, "noset")
    jmp("skip")             .side(0)
    label("noset")
    nop()
    label("skip")
    jmp(y_dec, "loop")


_PERIOD = 255                       # 8-bit samples map 1:1 onto the duty
_PIO0_TXF0 = 0x50200010             # PIO0 TX FIFO for SM0; +4 per SM
_DMA_TIMER0 = 0x50000420            # DMA pacing timers; +4 per timer
_TREQ_TIMER0 = 0x3B                 # DREQ number of DMA timer 0; +1 per timer


class WavError(Exception):
    pass


def _read_wav(path, max_bytes):
    """Return (rate, samples) with samples a bytearray of 8-bit PWM values.

    Walks the RIFF chunks properly (LIST/INFO chunks before 'data' are
    common) and stops reading at max_bytes of *samples*, so a long file
    just plays truncated instead of exhausting RAM.
    """
    with open(path, 'rb') as f:
        riff = f.read(12)
        if riff[:4] != b'RIFF' or riff[8:12] != b'WAVE':
            raise WavError('not a RIFF/WAVE file')
        rate = bits = channels = None
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                raise WavError('no data chunk')
            cid, size = struct.unpack('<4sI', hdr)
            if cid == b'fmt ':
                fmt = f.read(size)
                tag, channels, rate, _, _, bits = struct.unpack('<HHIIHH', fmt[:16])
                if tag != 1:
                    raise WavError('not PCM (format %d)' % tag)
                if channels != 1:
                    raise WavError('%d channels, need mono' % channels)
                if bits not in (8, 16):
                    raise WavError('%d-bit, need 8 or 16' % bits)
                if not 2000 <= rate <= 48000:
                    raise WavError('%d Hz out of range' % rate)
            elif cid == b'data':
                if rate is None:
                    raise WavError('data before fmt')
                break
            else:
                f.seek(size + (size & 1), 1)  # skip, chunks are word-aligned

        # Leave headroom for the rest of boot; a MemoryError here would
        # be a worse outcome than a shorter sound.
        gc.collect()
        budget = max(0, min(max_bytes, gc.mem_free() - 24 * 1024))
        n = size // (bits // 8)
        n = min(n, budget)
        if n <= 0:
            raise WavError('no room to load %d samples' % (size // (bits // 8)))
        buf = bytearray(n)
        if bits == 8:
            got = f.readinto(buf)   # 8-bit WAV is unsigned: already PWM values
            if got < n:
                buf = buf[:got]
        else:
            # 16-bit signed little-endian: the high byte with its sign
            # flipped is the unsigned 8-bit value. Chunked so the raw
            # read never needs a second full-size buffer.
            chunk = bytearray(2048)
            done = 0
            while done < n:
                want = min(len(chunk), 2 * (n - done))
                got = f.readinto(memoryview(chunk)[:want])
                if not got:
                    break
                for j in range(1, got, 2):
                    buf[done] = chunk[j] ^ 0x80
                    done += 1
            if done < n:
                buf = buf[:done]
    return rate, buf


def _timer_div(rate):
    """X/Y for a DMA pacing timer: ticks at sysclk * X / Y, both 16-bit."""
    clk = freq()
    x = min(65535, (65535 * rate) // clk)   # biggest X keeps Y precise
    x = max(1, x)
    y = min(65535, round(x * clk / rate))
    return x, y


class BootSound:
    """A sound in flight. Construct via play(); wait() then stop()."""

    def __init__(self, rate, buf, pin_a, pin_b):
        self.buf = buf                  # keep it referenced while DMA reads it
        self.pins = (pin_a, pin_b)
        self.sms = []
        self.dmas = []
        x, y = _timer_div(rate)
        for i, (pin, prog) in enumerate(((pin_a, _pwm_pos), (pin_b, _pwm_neg))):
            if pin is None:
                continue
            sm = rp2.StateMachine(i, prog, freq=freq(), sideset_base=Pin(pin))
            sm.put(_PERIOD)             # period -> ISR, once
            sm.exec("pull()")
            sm.exec("out(isr, 32)")
            sm.active(1)
            self.sms.append(sm)
            # One pacing timer per channel; sharing a DREQ between two
            # channels is not something to bet the boot on.
            mem32[_DMA_TIMER0 + 4 * i] = (x << 16) | y
            d = rp2.DMA()
            ctrl = d.pack_ctrl(size=0, inc_read=True, inc_write=False,
                               treq_sel=_TREQ_TIMER0 + i)
            d.config(read=buf, write=_PIO0_TXF0 + 4 * i, count=len(buf),
                     ctrl=ctrl, trigger=True)
            self.dmas.append(d)
        self.rate = rate

    def playing(self):
        return any(d.active() for d in self.dmas)

    def wait(self):
        while self.playing():
            time.sleep_ms(5)

    def stop(self):
        """Release PIO and DMA; leave the pins as plain outputs, low."""
        for d in self.dmas:
            d.active(0)
            d.close()
        for sm in self.sms:
            sm.active(0)
        self.dmas = []
        self.sms = []
        for pin in self.pins:
            if pin is not None:
                Pin(pin, Pin.OUT, value=0)
        self.buf = None
        gc.collect()


def play(path, max_bytes, pin_a, pin_b=None):
    """Start playing `path`; returns a BootSound, or None if it cannot.

    Never raises for a bad or missing file -- it prints why and returns
    None, so the caller's boot carries on unchanged.
    """
    try:
        rate, buf = _read_wav(path, max_bytes)
    except OSError:
        return None                     # no such file: the normal case
    except (WavError, ValueError, MemoryError) as e:
        print('bootsound: %s: %s' % (path, e))
        return None
    if not buf:
        return None
    return BootSound(rate, buf, pin_a, pin_b)
