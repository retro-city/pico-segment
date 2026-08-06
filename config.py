"""User settings for the front panel controller. Edit and re-deploy.

Speeds and turbo state are DEFAULTS for the first boot only: the
running values live in settings.json on the Pico (written on turbo
toggle and setup-mode save). Delete that file to return to these.
"""

from ht16k33_seg import RED, YELLOW, GREEN

# Speeds shown on the 3-digit display.
MHZ_TURBO = 133    # shown while turbo is on
MHZ_NORMAL = 66    # shown while turbo is off (None = always show MHZ_TURBO)

# Turbo state at power-on.
TURBO_ON_AT_BOOT = True

# Hold buttons A+B this long to enter setup mode (adjust MHz, A+B saves).
SETUP_HOLD_MS = 2000

# Turbo output to the motherboard: GP21, level-shifted to 5 V on J3 pin 1.
# High = turbo on.
TURBO_OUT_PIN = 21

# Fun segment-ring spin on the display when the speed changes.
SPIN_ANIMATION = True
SPIN_MS = 300        # total animation time
SPIN_FRAME_MS = 30   # time per frame (lower = faster spin)

# Reset passthrough: button A (SW1) is mirrored to GP20, which drives
# a PC817 optocoupler LED through 330R. The opto's phototransistor
# switches the PC's own 5 V into its active-high reset input (~3k
# pull-down), so the line is galvanically isolated. GP20 idles low
# (opto dark), goes high while pressed; the RP2040's pins-low boot
# state leaves the PC alone.
RESET_OUT_PIN = 20
RESET_ACTIVE_HIGH = True  # GP20 high = opto LED on = reset asserted

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

# Display brightness, 0..15.
BRIGHTNESS = 15
