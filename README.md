# Retro PC 7-segment display controller

MicroPython controller for the *Retro_PC-7_egment_display* board: a Pico W
driving a 3-digit seven segment display (SLR0563) and three front-panel LEDs
through an HT16K33A over I2C.

## Behavior

- The display shows the CPU speed: `mhz_turbo` (default 166) while turbo
  is on, `mhz_normal` (default 133) while it is off. Speeds and turbo
  state persist in `settings.json` on the Pico; `config.py` only
  provides first-boot defaults (delete `settings.json` to reset).
- **Setup mode**: hold A+B for 2 s (display shows `SEt`, release, value
  blinks). B (the right-hand button) = +1, A = −1, hold to auto-repeat;
  keep holding 2 s and steps become ±10. A+B saves and exits. The reset
  output is suspended during setup. Above 999 MHz the display switches to GHz
  with a decimal point (`1.00` … `9.99`, 10 MHz per step); stepping
  down from `1.00` returns to `999`.
- At power-on all three LEDs light for 2 seconds (lamp test), then only the
  **power** LED stays lit. Turbo starts on (`TURBO_ON_AT_BOOT`).
- **Turbo** toggles when button B (SW2) is *released*. The turbo LED
  follows it, and **GP20** (5 V on J3 pin 3) drives the motherboard:
  high = turbo on. Speed changes play a segment spin animation
  (`SPIN_ANIMATION`, `SPIN_MS`, `SPIN_FRAME_MS`). The toggle waits for
  the release so a long hold can claim the press for the clicker mute
  below without flipping the speed on its way there.
- **Reset**: button A (SW1) is mirrored to **GP21** (J3 pin 1) by pin
  interrupt: idles low, driven high while pressed
  (`RESET_ACTIVE_HIGH = True`).
  GP21 drives a PC817 optocoupler LED through 330 Ω; the opto's
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
- **HDD clicker**: a passive piezo on **GP22** (`CLICK_PIN`) clicks
  while that LED is lit, so the silent CF card still sounds like a
  drive seeking. There is no tone — a piezo disc clicks on a voltage
  *edge*, and a plain DC step is what the hardware HDD clickers feed
  theirs; a tone, however short, is a beep. A seek is two edges, one as
  the head "moves" and another `CLICK_HOLD_MS` later as it "lands" (the
  table is cycled so seeks are not all alike), spaced no closer than
  `CLICK_GAP_MS` — one brief access clicks once, a long transfer
  chatters. Nothing blocks. The piezo sits *between* GP22 and GP26
  (`CLICK_PIN`/`CLICK_PIN_B`), driven in antiphase so every edge swings
  6.6 V rather than the 3.3 V one pin can manage; `CLICK_PIN_B = None`
  for piezo-to-GND at half the swing. `CLICK_ENABLED = False` removes
  it entirely.
- **Clicker mute**: hold button B alone for `CLICK_MUTE_HOLD_MS` (3 s)
  to mute or unmute the clicker; the display scrolls `HDCLIC ON` /
  `HDCLIC OFF` (`CLICK_TEXT_ON`/`_OFF`) and the choice is saved in
  `settings.json` with the turbo state. Turbo is left alone.
- **Lock**: J1 (button C) is a maintained keyboard-lock switch and
  **GP19** (5 V on J3 pin 5) follows its position, high = locked
  (`LOCK_ACTIVE_HIGH`; `LOCK_SWITCH_ACTIVE_LOW` sets which way the
  switch reads). Nothing is persisted — the switch is read again at
  every boot. There is no spare LED, so the display is the indicator:
  it reads `LOC` (`LOCK_TEXT`) in place of the speed for as long as the
  switch is locked. Setup mode still shows the MHz being edited.
- **Easter egg**: hold reset (button A) for `EGG_HOLD_MS` (1 s). The
  drive "loads" the message: first a burst of faked activity —
  `HDD_BURST_PULSES` flashes of the HDD LED with a seek per flash, in
  the cycled uneven `HDD_BURST_ON_MS`/`_OFF_MS` times so it reads as a
  drive working rather than a blinking light — then `EGG_TEXT` scrolls
  past. The burst doubles as a check of the piezo and LED without
  waiting for the disk. Turbo is left alone.

LED roles default to power = LED2, turbo = LED3, HDD = LED4; remap them
in `config.py`. The code names the positions `RED`/`YELLOW`/`GREEN`
after the originally fitted colors, but the physical LEDs have since
been swapped for period-correct ones, so treat the names as positions.
Each `HDD_INPUTS` entry carries its own `active_low` flag — flip a
line's flag if its LED works inverted.

## Hardware map (from the KiCad schematics)

| Function | Wiring |
|---|---|
| I2C bus | Pico **GP4 = SDA**, **GP5 = SCL** (I2C0), PCA9306 shifts to 5 V |
| HT16K33A address | **0x70** (28-SSOP has no address pins) |
| Digits 1–3 (left→right) | COM0, COM1, COM2 |
| Segments | ROW0=A, ROW1=B, ROW2=C, ROW3=D, ROW4=E, ROW5=F, ROW6=G, ROW7=DP |
| LED2 (`RED` in code) | ROW8, cathode on COM3 |
| LED3 (`YELLOW` in code) | ROW9, cathode on COM3 |
| LED4 (`GREEN` in code) | ROW10, cathode on COM3 |
| Button A / B / C | SW1 / SW2 / J1 on GP8 / GP7 / GP6, active low, 10k pull-ups |
| GP18–21 | level-shifted to 5 V on J3 (odd pins signals, even pins GND): GP21 = reset out (J3-1), GP20 = turbo out (J3-3), GP19 = lock out (J3-5), GP18 = HDD in (J3-7) |
| GP22 + GP26 | HDD clicker: passive piezo *between* Pico pins 29 and 31, driven in antiphase by DC edges for a 6.6 V swing (`CLICK_PIN`/`CLICK_PIN_B`; not on J3). Pin 30 between them is RUN — keep solder off it. `CLICK_PIN_B = None` for piezo-to-GND at half the swing |

## Files

- `ht16k33_seg.py` — display driver (digits, text, numbers, scroll, LEDs, brightness, blink)
- `config.py` — user settings: speed, LED roles, HDD polarity, brightness
- `main.py` — the front panel controller described above
- `segtest.py` — board check: lights each segment/LED one at a time
- `firmware/RPI_PICO_W-v1.28.0.uf2` — stock MicroPython for the Pico W
- `firmware/manifest.py`, `firmware/build.sh` — build a UF2 with the
  panel frozen in (see [All-in-one UF2](#all-in-one-uf2))
- `firmware/verify_uf2.py` — checks a built image is a sane RP2040 UF2
  and really carries the frozen code
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

## All-in-one UF2

`firmware/build.sh` bakes the panel code into a MicroPython image, so a
board is set up by flashing one file — no `mpremote`, no serial port, no
copying scripts. Hold BOOTSEL while plugging the Pico in and drop the
image for that board from `out/` onto the `RPI-RP2` drive. Released
builds are attached to the GitHub release for the tag.

```sh
git clone --depth 1 --branch v1.28.0 \
    https://github.com/micropython/micropython.git ../micropython
make -C ../micropython/mpy-cross
make -C ../micropython/ports/rp2 BOARD=RPI_PICO_W submodules
firmware/build.sh                  # -> out/pico-segment-RPI_PICO_W-*.uf2
BOARD=RPI_PICO firmware/build.sh   # -> out/pico-segment-RPI_PICO-*.uf2
```

Needs `arm-none-eabi-gcc`, `cmake`, `make` and `git`; `MPY_DIR` overrides
where the MicroPython tree lives and `MPY_VERSION` overrides the version
in the filename. The build takes a few minutes the first time because it
compiles `picotool` too.

Pushing a `v*` tag builds both images in CI and attaches them to the
GitHub release as `pico-segment-<tag>-<board>.uf2`
(`.github/workflows/release.yml`).

**Match the image to the board.** A Pico W image on a genuine non-W Pico
hangs before `main.py` runs, so the display stays blank: the boot code
arms a *level-high* interrupt on GP24 for the CYW43's host-wake line
(`ports/rp2/mpnetworkport.c`), and on a plain Pico GP24 is the VBUS
sense pin, held high whenever USB power is present. The interrupt then
re-fires forever. Many clone boards leave GP24 low or floating and so
survive the mismatch, which makes it look board-specific rather than
firmware-specific.

Frozen modules are read-only and live beside the filesystem, which still
holds the writable `settings.json`. `sys.path` is `['', '.frozen']`, so a
`config.py` copied onto the board shadows the frozen one — speeds, LED
roles and polarities can still be changed without rebuilding. `main.py`
is the exception: the boot code looks for a frozen `main.py` *before* the
filesystem one, so changing it means a rebuild.

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

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

Bundled third-party components keep their own licenses: `tools/vendor/`
contains unmodified copies of
[mpremote](https://github.com/micropython/micropython/tree/master/tools/mpremote)
and [platformdirs](https://github.com/tox-dev/platformdirs), both MIT
(license texts in their `.dist-info/licenses/` directories), and
`firmware/RPI_PICO_W-v1.28.0.uf2` is the official MicroPython build for
the Pico W (also MIT).
