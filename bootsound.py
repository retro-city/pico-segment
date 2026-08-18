# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Play a WAV file through the piezo, streaming from flash.

The piezo hangs between two GPIOs (the HDD clicker's pins). Two PIO
state machines run an 8-bit PWM at ~62 kHz on them, one inverted, so
the disc sees the difference and swings the full 6.6 V; DMA feeds each
machine one sample per tick of a DMA pacing timer set to the WAV's rate.

The file streams: two 8 KB buffers, and per pin a pair of DMA channels
chained to each other in a ping-pong, so one buffer plays while the
other is refilled from the file. Refills run from the DMA completion
interrupt (soft, so they may touch the filesystem), which keeps them
going through anything the panel does meanwhile -- a 2.5 s scroll, a
flash write. So a track can be as long as the drive has room for, and
nothing waits for it: start it, service() it from the loop, and it
tells you when it is done.

    snd = bootsound.play('boot.wav', 22, 26)
    ...
    if snd and not snd.playing():
        snd.stop()               # release PIO/DMA, hand the pins back

Accepts mono PCM WAV, 8-bit unsigned or 16-bit signed, 2-48 kHz.
8-bit is the fast path: its samples ARE the PWM values, straight from
the file into the play buffer. 16-bit is converted chunk by chunk in a
Python loop, which keeps up at 16 kHz but only just, so convert on the
host with tools/wav2boot.py where you can. Stereo is refused rather
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
# 3 * 256 + 3 = 771 cycles a period: ~62 kHz at the 48 MHz the machines
# run at (see BootSound). pull(noblock)
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
_PIO_HZ = 48_000_000                # PWM carrier = _PIO_HZ / 771 = ~62 kHz, see below
_PADS_BANK0 = 0x4001C000            # pad control; GPIOn at +4 + 4n
_PIO0_TXF0 = 0x50200010             # PIO0 TX FIFO for SM0; +4 per SM
_DMA_TIMER0 = 0x50000420            # DMA pacing timers; +4 per timer
_TREQ_TIMER0 = 0x3B                 # DREQ number of DMA timer 0; +1 per timer


def stiff_pad(pin):
    """Drive a piezo pin as hard as the RP2040 allows: 12 mA, fast slew.

    A piezo disc is a capacitor of 10-30 nF, and what limits how fast
    (so how loudly) it moves is the current the pad can source. The
    default is 4 mA; MicroPython's Pin has no knob for it, so set the
    pad register directly. Survives Pin()/PIO re-init, which only touch
    the function and direction bits.
    """
    addr = _PADS_BANK0 + 4 + 4 * pin
    mem32[addr] = (mem32[addr] & ~0x30) | 0x30 | 0x01   # DRIVE=12mA, SLEWFAST


class WavError(Exception):
    pass



class WavError(Exception):
    pass


CHUNK = 8192            # samples per buffer; 512 ms at 16 kHz, 8 KB each


class _Wav:
    """An open WAV positioned at its data, handing out 8-bit chunks."""

    def __init__(self, path):
        self.f = open(path, 'rb')
        try:
            self._parse()
        except Exception:
            self.f.close()
            raise
        self._raw = bytearray(2 * CHUNK) if self.bits == 16 else None

    def _parse(self):
        f = self.f
        riff = f.read(12)
        if riff[:4] != b'RIFF' or riff[8:12] != b'WAVE':
            raise WavError('not a RIFF/WAVE file')
        rate = bits = None
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
                f.seek(size + (size & 1), 1)  # skip; chunks are word-aligned
        self.rate = rate
        self.bits = bits
        self.remaining = size // (bits // 8)   # samples left in the data chunk

    def fill(self, buf):
        """Put the next samples into buf; returns how many (0 = the end)."""
        want = min(len(buf), self.remaining)
        if want <= 0:
            return 0
        if self.bits == 8:
            got = self.f.readinto(memoryview(buf)[:want])   # unsigned: PWM values as-is
        else:
            # 16-bit signed little-endian: the high byte with its sign
            # flipped is the unsigned 8-bit value.
            raw = self.f.readinto(memoryview(self._raw)[:2 * want]) or 0
            got = raw // 2
            r = self._raw
            for j in range(got):
                buf[j] = r[2 * j + 1] ^ 0x80
        got = got or 0
        self.remaining -= got
        return got

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


def _timer_div(rate):
    """X/Y for a DMA pacing timer: ticks at sysclk * X / Y, both 16-bit."""
    clk = freq()
    x = min(65535, (65535 * rate) // clk)   # biggest X keeps Y precise
    x = max(1, x)
    y = min(65535, round(x * clk / rate))
    return x, y


class BootSound:
    """A sound in flight. Construct via play(); poll playing(); stop()."""

    def __init__(self, wav, pin_a, pin_b):
        self.wav = wav
        self.rate = wav.rate
        self.pins = (pin_a, pin_b)
        self.bufs = (bytearray(CHUNK), bytearray(CHUNK))
        self.sms = []
        self.chans = []          # per pin: [chan for buf 0, chan for buf 1]
        self.eof = False
        self.underrun = 0

        n0 = wav.fill(self.bufs[0])
        if n0 == 0:
            raise WavError('no samples')
        n1 = wav.fill(self.bufs[1])
        counts = (n0, n1)
        if n1 == 0:
            self.eof = True

        x, y = _timer_div(wav.rate)
        pins = [(p, prog) for p, prog in ((pin_a, _pwm_pos), (pin_b, _pwm_neg))
                if p is not None]
        for i, (pin, prog) in enumerate(pins):
            stiff_pad(pin)
            # 48 MHz, not the full 125: the piezo has to charge and
            # discharge through the pad every carrier period, and at
            # 163 kHz (6 us) a 20 nF disc at 12 mA cannot get near the
            # rails, so the PWM never delivers its swing. ~62 kHz (16 us)
            # is still far above hearing and gives it ~9 V of headroom.
            sm = rp2.StateMachine(i, prog, freq=_PIO_HZ, sideset_base=Pin(pin))
            sm.put(_PERIOD)             # period -> ISR, once
            sm.exec("pull()")
            sm.exec("out(isr, 32)")
            sm.active(1)
            self.sms.append(sm)
            # One pacing timer per pin; sharing a DREQ between channels
            # is not something to bet the boot on.
            mem32[_DMA_TIMER0 + 4 * i] = (x << 16) | y
            pair = [rp2.DMA(), rp2.DMA()]
            self.chans.append(pair)
            for k in (0, 1):
                d = pair[k]
                other = pair[1 - k]
                # Chain to the partner: when this buffer ends, the other
                # starts with no gap. If the partner holds the last
                # chunk, its chain is cut back to itself at refill time.
                chain = other.channel if not (self.eof and k == 0) else d.channel
                # irq_quiet=False: MicroPython's pack_ctrl silences the
                # completion IRQ by default, and the refills hang off it.
                # read_err/write_err=True: those bits are write-one-to-
                # clear, and a stale bus error left on a channel by an
                # earlier run halts it the moment it is triggered.
                ctrl = d.pack_ctrl(size=0, inc_read=True, inc_write=False,
                                   treq_sel=_TREQ_TIMER0 + i, chain_to=chain,
                                   irq_quiet=False, read_err=True, write_err=True)
                d.config(read=self.bufs[k], write=_PIO0_TXF0 + 4 * i,
                         count=counts[k], ctrl=ctrl, trigger=False)
                if i == 0:
                    # Only pin A's channels report; pin B runs in lockstep
                    # and is re-armed alongside from the same handler.
                    d.irq(handler=self._make_handler(k), hard=False)
        # Start every pin's first channel as close together as we can.
        for pair in self.chans:
            pair[0].config(trigger=True)

    def _make_handler(self, k):
        def handler(_):
            self._refill(k)
        return handler

    def _refill(self, k):
        """Buffer k just finished on pin A: reload it and re-arm."""
        if self.eof:
            return
        buf = self.bufs[k]
        # Pin B reads the same buffer a hair behind pin A; give it that hair.
        for pair in self.chans[1:]:
            t0 = time.ticks_us()
            while pair[k].active() and time.ticks_diff(time.ticks_us(), t0) < 2000:
                pass
        n = self.wav.fill(buf)
        if n == 0:
            # Nothing left: the partner buffer, now playing, is the last.
            # Cut its chain so it does not trigger this stale channel.
            self.eof = True
            for i, pair in enumerate(self.chans):
                other = pair[1 - k]
                other.ctrl = other.pack_ctrl(size=0, inc_read=True, inc_write=False,
                                             treq_sel=_TREQ_TIMER0 + i,
                                             chain_to=other.channel, irq_quiet=False,
                                             read_err=True, write_err=True)
            return
        for pair in self.chans:
            d = pair[k]
            if d.active():
                self.underrun += 1      # partner already chained into us
            d.config(read=buf, count=n, trigger=False)

    def playing(self):
        return any(d.active() for pair in self.chans for d in pair)

    def wait(self):
        while self.playing():
            time.sleep_ms(5)

    def stop(self):
        """Release PIO and DMA; leave the pins as plain outputs, low."""
        for pair in self.chans:
            for d in pair:
                d.irq(handler=None)
                d.active(0)
                d.close()
        for sm in self.sms:
            sm.active(0)
        self.chans = []
        self.sms = []
        for pin in self.pins:
            if pin is not None:
                Pin(pin, Pin.OUT, value=0)
        self.wav.close()
        self.bufs = None
        gc.collect()


def play(path, pin_a, pin_b=None):
    """Start playing `path`; returns a BootSound, or None if it cannot.

    Never raises for a bad or missing file -- it prints why and returns
    None, so the caller's boot carries on unchanged.
    """
    try:
        wav = _Wav(path)
    except OSError:
        return None                     # no such file: the normal case
    except (WavError, ValueError, MemoryError) as e:
        print('bootsound: %s: %s' % (path, e))
        return None
    try:
        return BootSound(wav, pin_a, pin_b)
    except (WavError, MemoryError) as e:
        wav.close()
        print('bootsound: %s: %s' % (path, e))
        return None
