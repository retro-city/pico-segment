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

# Reset passthrough: button A (SW1) is mirrored to GP20 (5 V on J3
# pin 3), through an NPN emitter follower to the motherboard's
# active-high reset input (~3k pull-down, too heavy for the TXB0104
# alone). GP20 idles low, goes high while pressed.
RESET_OUT_PIN = 20
RESET_ACTIVE_HIGH = True

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

# Motherboard HDD activity input on GP18 (via J3 pin 7 / TXB0104).
# This motherboard drives the line high during activity.
HDD_ACTIVE_LOW = False

# Minimum time the HDD LED stays lit per activity pulse, so very short
# bursts are still visible.
HDD_MIN_ON_MS = 50

# Display brightness, 0..15.
BRIGHTNESS = 15
