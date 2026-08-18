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
# passive piezo imitates the seek chatter of a mechanical drive. One tick
# is a short PWM burst; ticks repeat for as long as the activity LED is
# lit, no closer together than CLICK_GAP_MS, so a brief access gives a
# single click and a long transfer chatters instead of buzzing.
#
# Wire a passive piezo between CLICK_PIN and any GND pin. A bare disc can
# hang straight off the pin (it is capacitive and draws little at these
# frequencies); ~100R in series is a harmless precaution. An ACTIVE
# buzzer will not work — it has its own oscillator and ignores the tone.
CLICK_ENABLED = True
CLICK_PIN = 22
CLICK_FREQS = (1800, 2400, 2050, 2700)  # cycled, so ticks are not identical
CLICK_MS = 5          # length of one tick
CLICK_DUTY = 32768    # 16-bit duty; half is the loudest square wave
CLICK_GAP_MS = 60     # shortest spacing between ticks

# Display brightness, 0..15.
BRIGHTNESS = 15
