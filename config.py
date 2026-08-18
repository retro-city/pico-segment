# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""User settings for the front panel controller. Edit and re-deploy.

Speeds and turbo state are DEFAULTS for the first boot only: the
running values live in settings.json on the Pico (written on turbo
toggle and setup-mode save). Delete that file to return to these.
"""

from ht16k33_seg import RED, YELLOW, GREEN

# Speeds shown on the 3-digit display.
MHZ_TURBO = 166     # shown while turbo is on
MHZ_NORMAL = 133    # shown while turbo is off (None = always show MHZ_TURBO)

# Turbo state at power-on.
TURBO_ON_AT_BOOT = True

# Hold buttons A+B this long to enter setup mode (adjust MHz, A+B saves).
SETUP_HOLD_MS = 2000

# Turbo output to the motherboard: GP20, level-shifted to 5 V on J3 pin 3.
# High = turbo on.
TURBO_OUT_PIN = 20

# Keyboard-lock output to the motherboard: GP19, level-shifted to 5 V
# on J3 pin 5, driving an optocoupler LED. J1 (button C, GP6) is a
# maintained switch, so the output just follows its position — there is
# no saved state, and the switch is read again at every boot.
LOCK_OUT_PIN = 19
LOCK_ACTIVE_HIGH = True        # GP19 high = opto LED on = lock asserted
LOCK_SWITCH_ACTIVE_LOW = True  # J1 closed (GP6 pulled low) = locked

# Shown in place of the speed while locked, since the lock has no LED
# of its own.
LOCK_TEXT = 'LOC'

# Fun segment-ring spin on the display when the speed changes.
SPIN_ANIMATION = True
SPIN_MS = 300        # total animation time
SPIN_FRAME_MS = 30   # time per frame (lower = faster spin)

# Reset passthrough: button A (SW1) is mirrored to GP21 (J3 pin 1),
# which drives a PC817 optocoupler LED through 330R. The opto's
# phototransistor switches the PC's own 5 V into its active-high reset
# input (~3k pull-down), so the line is galvanically isolated. GP21
# idles low (opto dark), goes high while pressed; the RP2040's
# pins-low boot state leaves the PC alone.
RESET_OUT_PIN = 21
RESET_ACTIVE_HIGH = True  # GP21 high = opto LED on = reset asserted

# The display shows --- for this long when reset is pressed.
RESET_FLASH_MS = 300

# Hold reset this long for the easter egg.
EGG_HOLD_MS = 1000
EGG_TEXT = 'RETRO CITY'
EGG_SCROLL_MS = 250  # scroll speed per step

# LED roles. Board LEDs: RED = LED2 (ROW8), YELLOW = LED3 (ROW9),
# GREEN = LED4 (ROW10).
POWER_LED = RED
TURBO_LED = YELLOW
HDD_LED = GREEN

# HDD activity inputs: (pin, active_low, direct) — ANY line reading
# active lights the LED. direct=True marks a plain GPIO line: it gets
# an idle-bias pull (disconnected = quiet) and edge IRQs. TXB-backed
# lines must stay direct=False — a pull fights the TXB's keeper, and
# a slow edge (like an opto's) makes its one-shots oscillate, which
# with an IRQ armed storms and hangs the board. They are polled
# instead, missing nothing: the TXB latches the active level until
# the firmware kicks it back to idle.
#  - GP28: direct sense loom (mobo LED- pin, 10k pull-up to 3V3, 10k
#    series); the open-collector source sinks it low on activity.
#  - GP18: TXB0104 channel on J3 pin 7; a PC817 opto (collector on
#    the line, emitter to GND) sinks it low on activity.
HDD_INPUTS = (
    (28, True, True),
    (18, True, False),
)

# Minimum time the HDD LED stays lit per activity pulse, so very short
# bursts are still visible.
HDD_MIN_ON_MS = 50

# HDD clicker. The CF card standing in for the hard disk is silent, so a
# passive piezo imitates the seek noise of a mechanical drive.
#
# There is no tone. A piezo disc clicks on a voltage EDGE -- it flexes
# once and rings down at its own resonance -- and a plain DC step is what
# the hardware HDD clickers feed theirs; a tone, however short, is a
# beep. A seek is two edges: one as the head 'moves', another
# CLICK_HOLD_MS later as it 'lands' (the table is cycled so seeks are not
# all alike). Seeks repeat while the activity LED is lit, no closer than
# CLICK_GAP_MS, so a brief access clicks once and a long transfer
# chatters.
#
# The piezo sits BETWEEN the two pins, no ground: they are driven in
# antiphase, so every edge swings 6.6 V rather than the 3.3 V a single
# pin can manage. GP22 is Pico pin 29 and GP26 is pin 31 -- pin 30
# between them is RUN, the reset line, so keep solder off it. A bare
# disc can hang straight across the pins (it is capacitive); ~100R in
# series is a harmless precaution. Set CLICK_PIN_B = None for a plain
# piezo-to-GND wiring at half the swing. An ACTIVE buzzer will not
# work: it has its own oscillator and just drones while the line is high.
CLICK_ENABLED = True
CLICK_PIN = 22
CLICK_PIN_B = 26
CLICK_HOLD_MS = (18, 26, 14, 32, 22)    # move-to-land, per seek, cycled
CLICK_GAP_MS = 60                       # shortest spacing between seeks

# Hold button B alone this long to mute/unmute the clicker; the choice
# is saved with the other settings. The display scrolls the new state.
CLICK_MUTE_HOLD_MS = 3000
CLICK_TEXT_ON = 'HDCLIC ON'
CLICK_TEXT_OFF = 'HDCLIC OFF'
CLICK_TEXT_SCROLL_MS = 200

# USB drive (the PICO / PICO_W images): the Pico's filesystem shows up on
# any computer as a drive called PICOSEGMENT holding settings.json and
# boot.wav. While a computer is attached it owns the drive -- the panel
# keeps setting changes in RAM and flashes this text instead of saving,
# then writes them out (or adopts an edited settings.json) when the
# cable comes out. Powered only by USB there is no "cable out" moment
# before power is lost, so on the bench edit settings.json on the drive.
USB_TEXT = 'USb'
USB_FLASH_MS = 700

# Boot sound: a WAV on the Pico's filesystem, played through the piezo
# during the power-on lamp test. Copy it over with
#   tools/mpr cp boot.wav :
# (or onto the USB drive). Mono PCM, 8-bit unsigned is the fast path --
# tools/wav2boot.py makes one from any WAV. 16 kHz suits a piezo: it
# cannot do much below ~1 kHz, so bass is wasted bytes. RAM caps the
# length; longer files play truncated. None disables it. Needs the
# clicker pins (CLICK_ENABLED), since that is the speaker.
BOOT_SOUND = 'boot.wav'
BOOT_SOUND_MAX_KB = 96      # ~6 s at 16 kHz 8-bit
# On a freshly formatted filesystem (nothing on the drive at all) write
# the built-in default -- sounds/spinup.wav, frozen in as
# defaultsound.py -- so there is something to hear and to replace.
# Delete boot.wav afterwards to silence it; it only comes back if
# settings.json is deleted too (a full reset).
BOOT_SOUND_SEED_DEFAULT = True

# The drive burst played by the easter egg (hold reset): the HDD LED
# flashes with a seek per flash, in these cycled uneven on/off times, so
# it reads as a drive working rather than a blinking light. Doubles as a
# way to check the piezo and LED without waiting for the disk.
HDD_BURST_PULSES = 14
HDD_BURST_ON_MS = (20, 45, 30, 60)
HDD_BURST_OFF_MS = (35, 20, 70, 25)

# Display brightness, 0..15.
BRIGHTNESS = 15
