# Retro PC 7-segment display controller

MicroPython controller for the *Retro_PC-7_egment_display* board: a Pico W
driving a 3-digit seven segment display (SLR0563) and three front-panel LEDs
through an HT16K33A over I2C.

## Behavior

- The display shows the CPU speed: `mhz_turbo` (default 133) while turbo
  is on, `mhz_normal` (default 66) while it is off. Speeds and turbo
  state persist in `settings.json` on the Pico; `config.py` only
  provides first-boot defaults (delete `settings.json` to reset).
- **Setup mode**: hold A+B for 2 s (display shows `SEt`, release, value
  blinks). A = +1, B = −1, hold to auto-repeat; keep holding 2 s and
  steps become ±10. A+B together saves and exits. The reset output is
  suspended during setup. Above 999 MHz the display switches to GHz
  with a decimal point (`1.00` … `9.99`, 10 MHz per step); stepping
  down from `1.00` returns to `999`.
- At power-on all three LEDs light for 2 seconds (lamp test), then only the
  **power** LED stays lit. Turbo starts on (`TURBO_ON_AT_BOOT`).
- **Turbo** toggles with button B (SW2). The turbo LED follows it, and
  **GP21** (5 V on J3 pin 1) drives the motherboard: high = turbo on.
  Speed changes play a segment spin animation (`SPIN_ANIMATION`,
  `SPIN_MS`, `SPIN_FRAME_MS`).
- **Reset**: button A (SW1) is mirrored to **GP20** by pin interrupt:
  idles low, driven high while pressed (`RESET_ACTIVE_HIGH = True`).
  GP20 drives a PC817 optocoupler LED through 330 Ω; the opto's
  phototransistor switches the PC's own 5 V into its active-high reset
  input (~3 kΩ pull-down), galvanically isolating the line. The
  RP2040's pins-low boot state leaves the opto dark, so Pico
  reboots/deploys can't reset the PC. The display shows `---` for
  `RESET_FLASH_MS` while rebooting.
- The **HDD** LED mirrors disk activity on every input in
  `HDD_INPUTS` — by default GP28 (direct sense loom on the mobo HDD
  LED header, active low) and GP18 (TXB channel on J3 pin 7, pulled
  low by an opto on activity); any active line lights it. Direct lines
  are caught by interrupt; TXB lines are polled only (the opto's slow
  edges make the TXB oscillate, which would storm an IRQ — its latch
  holds each pulse until polled instead). Pulses are stretched to
  `HDD_MIN_ON_MS` so short bursts stay visible.
- Easter egg: hold reset for 5 s (`EGG_HOLD_MS`).

LED roles default to power = LED2 (red), turbo = LED3 (yellow),
HDD = LED4 (green); remap them in `config.py`. `HDD_ACTIVE_LOW = True`
assumes the motherboard pulls the line low during activity — flip it if the
LED works inverted.

## Hardware map (from the KiCad schematics)

| Function | Wiring |
|---|---|
| I2C bus | Pico **GP4 = SDA**, **GP5 = SCL** (I2C0), PCA9306 shifts to 5 V |
| HT16K33A address | **0x70** (28-SSOP has no address pins) |
| Digits 1–3 (left→right) | COM0, COM1, COM2 |
| Segments | ROW0=A, ROW1=B, ROW2=C, ROW3=D, ROW4=E, ROW5=F, ROW6=G, ROW7=DP |
| Red LED (LED2) | ROW8, cathode on COM3 |
| Yellow LED (LED3) | ROW9, cathode on COM3 |
| Green LED (LED4) | ROW10, cathode on COM3 |
| Button SW1 / SW2 / J1 | GP8 / GP7 / GP6, active low, 10k pull-ups |
| GP18–21 | level-shifted to 5 V on header J3 (unused here) |

## Files

- `ht16k33_seg.py` — display driver (digits, text, numbers, scroll, LEDs, brightness, blink)
- `config.py` — user settings: speed, LED roles, HDD polarity, brightness
- `main.py` — the front panel controller described above
- `segtest.py` — board check: lights each segment/LED one at a time
- `firmware/RPI_PICO_W-v1.28.0.uf2` — MicroPython for the Pico W
- `tools/mpr` — vendored `mpremote` wrapper (this machine has no pip; only
  system `pyserial` is needed)

## First-time setup

1. **Serial permissions** (once): `sudo usermod -aG dialout $USER`, then log
   out and back in.
2. **Flash MicroPython** (once): hold BOOTSEL while plugging in the Pico, then
   copy `firmware/RPI_PICO_W-v1.28.0.uf2` onto the `RPI-RP2` drive that
   appears. The board reboots into MicroPython and shows up as `/dev/ttyACM0`.

## Deploy and run

```sh
tools/mpr cp ht16k33_seg.py config.py main.py segtest.py :   # copy to board
tools/mpr run segtest.py                           # verify every segment/LED
tools/mpr reset                                    # reboot -> front panel runs
```

## Using the driver interactively

```sh
tools/mpr exec "from ht16k33_seg import *; d = SegmentDisplay(); d.show('4.2')"
tools/mpr repl    # Ctrl-] to exit; Ctrl-C first to stop main.py
```

```python
from ht16k33_seg import SegmentDisplay, RED, YELLOW, GREEN
d = SegmentDisplay()          # opens I2C0 on GP4/GP5 itself
d.show('42')                  # right-aligned text
d.show('1.5.0.')              # dots ride on the preceding digit
d.number(3.14159)             # -> "3.14", best precision that fits
d.number(-7)
d.scroll('HELLO')             # blocking scroll
d.digit(0, 'A', dot=True)     # single digit, 0 = leftmost
d.raw(2, 0b01000000)          # raw segment bits, bit0=A..bit7=DP
d.leds(red=True, green=False) # named status LEDs
d.led(YELLOW, True)
d.brightness(4)               # 0..15
d.blink(2)                    # whole display: 0=off 1=2Hz 2=1Hz 3=0.5Hz
d.clear()
```

Batching: set `d.autoshow = False`, make several changes, then `d.update()`
pushes the buffer in one I2C write.

Note: HT16K33 brightness and blink are chip-wide — they affect the digits and
the three status LEDs together.
