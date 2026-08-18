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
- **Boot sound**: if a `boot.wav` is on the Pico's filesystem it plays
  through the piezo from power-on (`boot_sound` in `settings.json`).
  It **streams from flash**, so it can be a whole track: 16 kHz 8-bit
  is 16 KB/s, and about 80 s fits a plain Pico's 1.4 MB drive (50 s on
  a Pico W). Mono PCM, 8 or 16-bit, 2–48 kHz; 8-bit is the fast path
  and `tools/wav2boot.py` makes one from any WAV. 16 kHz suits a piezo
  — it barely moves below ~1 kHz, so bass is wasted bytes. Playback is
  PIO + DMA on the clicker pins (one machine per pin, one inverted, so
  the disc sees the full 6.6 V swing; ~62 kHz carrier, chosen so the
  disc can actually charge to the rails each cycle), double-buffered
  with refills from the DMA interrupt, so it costs the CPU next to
  nothing and the panel runs as normal while it plays — the clicker
  just waits for its pins until the sound ends, and pressing reset cuts
  it. Many stock sounds sit well below full scale (Windows 95's ding
  peaks at 46 %); pass `--normalize` to `wav2boot.py` for the missing
  6 dB. A bad file is
  reported on the serial console and skipped; the panel never fails to
  boot over a sound. `sounds/spinup.wav` is a synthesized drive
  spin-up to start from (`tools/mkspinup.py` regenerates it).
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
  for piezo-to-GND at half the swing. The pads are set to their 12 mA
  drive with fast slew (a piezo is a capacitor; current is what moves
  it), so no series resistor — it would only slow the edges. Beyond
  that, loudness is mechanical: a disc dangling on its wires is quiet;
  glued by its rim over a hole in a panel, with air behind it, the same
  disc is several times louder. `CLICK_ENABLED = False` removes it
  entirely.
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
- `config.py` — defaults and hardware facts: pins, polarities, LED roles
- `prefs.py` — the adjustable settings table, persisted in `settings.json`
- `boot.py`, `seed.py` — run before USB; give a fresh drive its files
- `main.py` — the front panel controller described above
- `segtest.py` — board check: lights each segment/LED one at a time
- `bootsound.py` — WAV player for the piezo (PIO PWM + DMA)
- `sounds/spinup.wav` — the default boot sound; `tools/mkspinup.py` made it
- `sounds/DING.WAV`, `sounds/ding.wav` — the Windows 95 ding, as found and
  normalized to full scale (`wav2boot.py --normalize`)
- `sounds/beep4k.wav` — POST-style beep, full-scale 4 kHz square: the loudest
  thing a 4 kHz piezo can make; `sounds/sweep.wav` — 0.5→10 kHz glide to hear
  where a disc's resonance is (`tools/mktone.py` makes both)
- `defaultsound.py` — the same WAV as a frozen module, seeded onto a fresh
  drive as `boot.wav` (`tools/mkdefaultsound.py` regenerates it)
- `tools/wav2boot.py` — converts any WAV to the panel's 8-bit mono format
- `firmware/RPI_PICO_W-v1.28.0.uf2` — stock MicroPython for the Pico W
- `firmware/manifest.py`, `firmware/build.sh` — build a UF2 with the
  panel frozen in (see [All-in-one UF2](#all-in-one-uf2))
- `firmware/boards/PICO`, `PICO_W` — the panel's own board definitions:
  stock Pico / Pico W plus the [USB drive](#the-usb-drive)
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
tools/mpr cp ht16k33_seg.py config.py main.py bootsound.py segtest.py :   # copy to board
tools/mpr cp sounds/spinup.wav :boot.wav           # optional boot sound
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
firmware/build.sh                  # -> out/pico-segment-PICO_W-*.uf2
BOARD=PICO firmware/build.sh       # -> out/pico-segment-PICO-*.uf2
```

`PICO_W` and `PICO` are the panel's own boards in `firmware/boards/`:
the stock Pico W / Pico definitions plus the USB drive below. The stock
names (`BOARD=RPI_PICO_W`, `RPI_PICO`) still build plain images without
the drive.

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

## The USB drive

With a `PICO`/`PICO_W` image the panel shows up on any computer as a
removable drive named **PICOSEGMENT** (plus the usual serial port).
Since the code is frozen, the drive holds just two things, and the
panel puts them there itself:

- `settings.json` — everything adjustable, one key per line:

  | key | what |
  |---|---|
  | `turbo` | turbo on/off |
  | `mhz_turbo`, `mhz_normal` | the two speeds (`mhz_normal: null` = always show turbo) |
  | `brightness` | display 0–15 |
  | `spin_animation` | segment spin on speed change |
  | `clicker` | HDD clicker on/off (what the B hold toggles) |
  | `click_hold_ms` | list; a seek's two edges are this far apart, cycled |
  | `click_gap_ms` | shortest spacing between seeks |
  | `hdd_min_on_ms` | how long an activity pulse keeps the LED (and clicks) going |
  | `boot_sound` | file to play at power-on; `null` for none |
  | `egg_text` | what the easter egg scrolls |

  Edit it and unplug; the panel adopts it the moment the cable comes
  out (`boot_sound` at the next power-on). Values are validated on the
  way in, so a typo cannot wedge the panel — a bad value keeps the
  previous one. Recreated with defaults whenever it is missing (delete
  it to reset). Hardware facts — pins, polarities, which HDD lines exist
  — stay in `config.py`; a `config.py` copied onto the drive shadows the
  frozen one, so even those can be changed without a rebuild.
- `boot.wav` — the boot sound. Replace it with your own, or delete it
  for silence. A freshly formatted drive gets the built-in default
  (`sounds/spinup.wav`, frozen in as `defaultsound.py`); it only comes
  back if `settings.json` is deleted as well, i.e. a full reset.

The drive is the raw filesystem, shared between the PC's driver and the
panel's own FAT code with no locking, so **while a computer is attached
the computer owns the drive**. The panel keeps setting changes made in
that time in RAM (turbo still switches, setup still works) and flashes
`USb` on the display where it would have saved; when the host goes it
writes them out — unless the host edited `settings.json` in the
meantime, in which case the file wins. Two consequences worth knowing:

- Powered **only by USB** there is no "cable out" moment before the
  power goes, so on the bench, changes made with the buttons are not
  saved. Edit `settings.json` on the drive instead, or power the panel
  from the PSU as installed and use USB just for the drive.
- `tools/mpr cp` writes from the panel's side; if the drive is mounted
  on the PC at the time, the PC's view goes stale until it remounts.
  Eject the drive first, or just use the drive.

The first boot after flashing over a plain image reformats the flash to
FAT (the drive needs FAT); `settings.json` and `boot.wav` from before
are lost, so copy them back. The `RPI_PICO*` images keep LittleFS and
have no drive.

Windows note: MicroPython's stock USB VID/PID is kept, and Windows
caches a device's descriptors per VID/PID — if a plain-image Pico was
plugged in before, the drive may not appear until that cached entry is
removed in Device Manager.

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
