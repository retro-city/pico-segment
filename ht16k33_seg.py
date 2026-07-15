"""Driver for the Retro PC 7-segment display board.

Hardware (from KiCad schematics, Retro_PC-7_egment_display):
  - HT16K33A-28SSOP at fixed I2C address 0x70, on the 5 V side of a
    PCA9306 level shifter. Pico W: GP4 = SDA, GP5 = SCL (I2C0).
  - COM0..COM2 = digits 1..3 (left to right), segments on ROW0..ROW7
    in standard order: ROW0=A, ROW1=B, ... ROW6=G, ROW7=DP.
  - COM3 = cathodes of three discrete LEDs; anodes on
    ROW8 = red, ROW9 = yellow, ROW10 = green.

Works under MicroPython. The class takes any I2C-like object with
writeto()/writeto_mem(), so the formatting logic is also testable
under CPython with a fake bus.
"""

# HT16K33 command bytes
_CMD_SYSTEM = 0x20  # | 1 = oscillator on
_CMD_DISPLAY = 0x80  # | (blink << 1) | on
_CMD_ROWINT = 0xA0  # INT/ROW15 pin acts as ROW output
_CMD_BRIGHT = 0xE0  # | level (0..15)

# LED index constants (bit within the high byte of COM3)
RED = 0     # ROW8,  board LED2, L-403SRD
YELLOW = 1  # ROW9,  board LED3, L-403YD
GREEN = 2   # ROW10, board LED4, L-403GD

# Segment bit order: bit0=A .. bit6=G, bit7=DP
FONT = {
    '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F, '4': 0x66,
    '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F,
    'A': 0x77, 'b': 0x7C, 'C': 0x39, 'c': 0x58, 'd': 0x5E,
    'E': 0x79, 'F': 0x71, 'G': 0x3D, 'H': 0x76, 'h': 0x74,
    'I': 0x30, 'J': 0x1E, 'L': 0x38, 'n': 0x54, 'O': 0x3F,
    'o': 0x5C, 'P': 0x73, 'q': 0x67, 'r': 0x50, 'S': 0x6D,
    't': 0x78, 'U': 0x3E, 'u': 0x1C, 'y': 0x6E,
    '-': 0x40, '_': 0x08, ' ': 0x00, "'": 0x20, '"': 0x22,
    '=': 0x48, '*': 0x63, '?': 0x53,
}


def glyph(ch):
    """Segment bits for a character; tries both cases, blank if unknown."""
    for c in (ch, ch.upper(), ch.lower()):
        if c in FONT:
            return FONT[c]
    return 0x00


def _cells(text):
    """Split text into (char, dot) cells; a '.' attaches to the char before it."""
    cells = []
    for ch in str(text):
        if ch == '.' and cells and not cells[-1][1]:
            cells[-1] = (cells[-1][0], True)
        elif ch == '.':
            cells.append((' ', True))
        else:
            cells.append((ch, False))
    return cells


class SegmentDisplay:
    """3-digit seven segment display + 3 status LEDs on an HT16K33A."""

    DIGITS = 3

    def __init__(self, i2c=None, addr=0x70, brightness=15):
        if i2c is None:
            from machine import I2C, Pin
            i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=400_000)
        self.i2c = i2c
        self.addr = addr
        self.buf = bytearray(16)  # HT16K33 display RAM mirror
        self.autoshow = True      # push buffer to the chip on every change

        if addr not in i2c.scan():
            raise OSError('HT16K33 not found at 0x%02X (scan: %s)'
                          % (addr, [hex(a) for a in i2c.scan()]))

        self._write_cmd(_CMD_SYSTEM | 1)   # oscillator on
        self._write_cmd(_CMD_ROWINT)       # INT pin as ROW driver (unused)
        self.update()                      # clear RAM before enabling output
        self._blink = 0
        self._on = 1
        self._write_display_cmd()
        self.brightness(brightness)

    # --- low level -----------------------------------------------------

    def _write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes([cmd]))

    def _write_display_cmd(self):
        self._write_cmd(_CMD_DISPLAY | (self._blink << 1) | self._on)

    def _sync(self):
        if self.autoshow:
            self.update()

    def update(self):
        """Push the local buffer to the chip (needed if autoshow=False)."""
        self.i2c.writeto_mem(self.addr, 0x00, self.buf)

    # --- display-wide controls ------------------------------------------

    def brightness(self, level):
        """PWM brightness, 0 (dimmest) .. 15 (full)."""
        self._write_cmd(_CMD_BRIGHT | (max(0, min(15, level)) & 0x0F))

    def blink(self, rate):
        """Blink whole display: 0=steady, 1=2 Hz, 2=1 Hz, 3=0.5 Hz."""
        self._blink = rate & 0x03
        self._write_display_cmd()

    def on(self):
        self._on = 1
        self._write_display_cmd()

    def off(self):
        self._on = 0
        self._write_display_cmd()

    def clear(self):
        for i in range(len(self.buf)):
            self.buf[i] = 0
        self._sync()

    # --- digits ----------------------------------------------------------

    def raw(self, pos, bits):
        """Set raw segment bits (bit0=A..bit6=G, bit7=DP) for digit 0..2."""
        self.buf[2 * pos] = bits & 0xFF
        self._sync()

    def digit(self, pos, ch, dot=False):
        """Show one character on digit pos (0=left)."""
        self.raw(pos, glyph(ch) | (0x80 if dot else 0))

    def show(self, text, align='right'):
        """Show a string, e.g. '42', '1.5', '-7', 'End'.

        A '.' rides on the preceding character, so '1.5.0.' fills all
        three decimal points. Longer strings are cut to 3 cells.
        """
        cells = _cells(text)[:self.DIGITS]
        pad = [(' ', False)] * (self.DIGITS - len(cells))
        cells = pad + cells if align == 'right' else cells + pad
        auto, self.autoshow = self.autoshow, False
        for pos, (ch, dot) in enumerate(cells):
            self.digit(pos, ch, dot)
        self.autoshow = auto
        self._sync()

    def number(self, n):
        """Show an int (-99..999) or float, best precision that fits."""
        if isinstance(n, float):
            for prec in (2, 1, 0):
                s = '%.*f' % (prec, n)
                if len(s.replace('.', '')) <= self.DIGITS:
                    self.show(s)
                    return
            n = int(n)  # too wide as float; fall through as int
        s = str(n)
        self.show(s if len(s) <= self.DIGITS else '---')

    def scroll(self, text, delay_ms=300):
        """Scroll text through the display, blocking."""
        import time
        sleep_ms = getattr(time, 'sleep_ms', lambda ms: time.sleep(ms / 1000))
        pad = [(' ', False)] * self.DIGITS
        cells = pad + _cells(text) + pad
        for i in range(len(cells) - self.DIGITS + 1):
            auto, self.autoshow = self.autoshow, False
            for pos, (ch, dot) in enumerate(cells[i:i + self.DIGITS]):
                self.digit(pos, ch, dot)
            self.autoshow = auto
            self._sync()
            sleep_ms(delay_ms)

    # --- status LEDs (COM3) ----------------------------------------------

    def led(self, idx, on=True):
        """Switch one LED: idx RED(0)/YELLOW(1)/GREEN(2)."""
        if on:
            self.buf[7] |= 1 << idx
        else:
            self.buf[7] &= ~(1 << idx)
        self._sync()

    def leds(self, red=None, yellow=None, green=None):
        """Set several LEDs at once; None leaves that LED unchanged."""
        auto, self.autoshow = self.autoshow, False
        for idx, state in ((RED, red), (YELLOW, yellow), (GREEN, green)):
            if state is not None:
                self.led(idx, state)
        self.autoshow = auto
        self._sync()
