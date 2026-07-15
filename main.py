"""Retro PC front panel controller, runs at boot.

Behavior:
  - Display shows the CPU speed: mhz_turbo while turbo is on,
    mhz_normal while it is off. Speeds and turbo state persist in
    settings.json; config.py supplies first-boot defaults.
  - All three LEDs light for 2 s at power-on, then only the power LED
    stays lit.
  - Button B (SW2, GP7) toggles turbo: turbo LED follows, GP21 (5 V on
    J3 pin 1) drives the motherboard (high = turbo on), state is saved,
    and the speed change plays a spin animation.
  - Button A (SW1, GP8) is the reset button, mirrored to GP20 (5 V on
    J3 pin 3) with config polarity; the display flashes ---.
    Hold A alone for a second for a surprise.
  - Hold A+B for SETUP_HOLD_MS to enter setup: the speed for the
    current turbo state blinks; A = +1 MHz, B = -1 MHz (hold to
    repeat), A+B together saves and exits. The reset output to the
    motherboard is suspended while setup is open.
  - The HDD LED mirrors the motherboard HDD activity signal on GP18,
    with short pulses latched by IRQ and stretched so they stay
    visible, and the level shifter's latch kicked back to idle.
"""

import json
import time
from machine import Pin

import config
from ht16k33_seg import SegmentDisplay

BTN_TURBO = Pin(7, Pin.IN)   # SW2 / BUTT-B, active low, external pull-up
BTN_RESET = Pin(8, Pin.IN)   # SW1 / BUTT-A, active low, external pull-up
HDD_IN = Pin(18, Pin.IN)     # HDD activity from motherboard via TXB0104
TURBO_OUT = Pin(config.TURBO_OUT_PIN, Pin.OUT)
RESET_OUT = Pin(config.RESET_OUT_PIN, Pin.OUT)

COMBO_GRACE_MS = 200   # window for the second button of the A+B combo
STEP_GRACE_MS = 150    # setup: tell a +-1 step apart from an A+B save
STEP_HOLD_MS = 450     # setup: hold this long before auto-repeat
STEP_REPEAT_MS = 80    # setup: auto-repeat interval for +-1 steps
BIG_STEP_HOLD_MS = 2000  # setup: hold this long and steps become +-10
BIG_STEP_REPEAT_MS = 240  # setup: slower auto-repeat while stepping +-10

# The adjustable speed runs on a display grid: 1 MHz steps up to 999,
# then 10 MHz steps shown as GHz with two decimals (1.00 ... 9.99).
MHZ_MAX = 9990
_IDX_MAX = 999 + (MHZ_MAX - 1000) // 10 + 1


def _mhz_to_idx(mhz):
    return mhz if mhz <= 999 else 999 + (mhz - 1000) // 10 + 1


def _idx_to_mhz(idx):
    return idx if idx <= 999 else 1000 + (idx - 1000) * 10


def show_mhz(disp, mhz):
    """MHz as-is up to 999; above that as GHz, DP on the first digit."""
    if mhz <= 999:
        disp.number(mhz)
    else:
        disp.show('%d.%02d' % (mhz // 1000, (mhz % 1000) // 10))


class Settings:
    """Persistent state: turbo flag and both MHz values."""

    PATH = 'settings.json'

    def __init__(self):
        self.turbo = config.TURBO_ON_AT_BOOT
        self.mhz_turbo = config.MHZ_TURBO
        self.mhz_normal = config.MHZ_NORMAL
        try:
            with open(self.PATH) as f:
                d = json.load(f)
            self.turbo = bool(d.get('turbo', self.turbo))
            self.mhz_turbo = self._clamp(d.get('mhz_turbo', self.mhz_turbo))
            n = d.get('mhz_normal', self.mhz_normal)
            self.mhz_normal = None if n is None else self._clamp(n)
        except (OSError, ValueError):
            pass  # missing or corrupt file -> config.py defaults

    @staticmethod
    def _clamp(mhz):
        return min(MHZ_MAX, max(1, int(mhz)))

    def save(self):
        try:
            with open(self.PATH, 'w') as f:
                json.dump({'turbo': self.turbo,
                           'mhz_turbo': self.mhz_turbo,
                           'mhz_normal': self.mhz_normal}, f)
        except OSError:
            pass  # keep running even if the flash write fails


class DebouncedPin:
    """Debounced active-low button with press timing."""

    def __init__(self, pin, debounce_ms=30):
        self.pin = pin
        self.debounce = debounce_ms
        self.stable = pin.value()
        self._raw = self.stable
        self._raw_t = time.ticks_ms()
        self.since = self._raw_t  # when .stable last changed

    def update(self):
        """Refresh; True when the stable state just changed."""
        v = self.pin.value()
        now = time.ticks_ms()
        if v != self._raw:
            self._raw = v
            self._raw_t = now
        elif v != self.stable and \
                time.ticks_diff(now, self._raw_t) >= self.debounce:
            self.stable = v
            self.since = now
            return True
        return False

    @property
    def down(self):
        return self.stable == 0

    def held_ms(self):
        return time.ticks_diff(time.ticks_ms(), self.since) if self.down else 0


# --- reset passthrough -------------------------------------------------

_reset_mirror_on = True


def _mirror_reset(pin=BTN_RESET):
    if _reset_mirror_on:
        pressed = pin.value() == 0
        RESET_OUT.value(pressed if config.RESET_ACTIVE_HIGH else not pressed)


def set_reset_mirror(enabled):
    """Enable/disable the button-A -> GP20 mirror (off during setup)."""
    global _reset_mirror_on
    _reset_mirror_on = enabled
    if enabled:
        _mirror_reset()
    else:
        RESET_OUT.value(0 if config.RESET_ACTIVE_HIGH else 1)  # inactive


# --- HDD activity input ------------------------------------------------

hdd_pulse = False
_HDD_TRIG = Pin.IRQ_FALLING if config.HDD_ACTIVE_LOW else Pin.IRQ_RISING


def _hdd_irq(_pin):
    global hdd_pulse
    hdd_pulse = True


def hdd_active():
    return HDD_IN.value() == (0 if config.HDD_ACTIVE_LOW else 1)


def kick_hdd_line():
    """Re-arm the HDD input after the motherboard releases it.

    The motherboard only ever drives the active level; when it lets go,
    the TXB0104 level shifter holds whatever was driven last, so the
    line would read active forever. Briefly driving the idle level from
    this side resets it. If the motherboard is still mid-activity it
    overpowers the shifter immediately and we get a fresh IRQ edge.
    """
    HDD_IN.init(Pin.OUT, value=1 if config.HDD_ACTIVE_LOW else 0)
    time.sleep_us(20)
    HDD_IN.init(Pin.IN)
    HDD_IN.irq(handler=_hdd_irq, trigger=_HDD_TRIG)
    time.sleep_us(50)  # let the line settle before it is read again


# --- display bits -------------------------------------------------------

def spin(disp):
    """Segment-ring spinner across all digits, phase-shifted per digit."""
    ring = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20)  # A,B,C,D,E,F clockwise
    for frame in range(config.SPIN_MS // config.SPIN_FRAME_MS):
        auto, disp.autoshow = disp.autoshow, False
        for pos in range(disp.DIGITS):
            disp.raw(pos, ring[(frame + 2 * pos) % 6])
        disp.autoshow = auto
        disp.update()
        time.sleep_ms(config.SPIN_FRAME_MS)


def easter_egg(disp):
    spin(disp)
    disp.scroll(config.EGG_TEXT, config.EGG_SCROLL_MS)
    spin(disp)


# --- setup mode ---------------------------------------------------------

class Stepper:
    """One setup button: step once after a grace period, then repeat.

    Steps are display units (+-1); after BIG_STEP_HOLD_MS of holding
    the same button they grow to +-10.
    """

    def __init__(self, btn, delta):
        self.btn = btn
        self.delta = delta
        self.pend = None      # press awaiting the grace period
        self.next_rep = None  # next auto-repeat due
        self.rep_ms = STEP_REPEAT_MS

    def _step(self):
        big = self.btn.held_ms() >= BIG_STEP_HOLD_MS
        self.rep_ms = BIG_STEP_REPEAT_MS if big else STEP_REPEAT_MS
        return self.delta * (10 if big else 1)

    def poll(self, now, edge):
        d = 0
        if edge and self.btn.down:
            self.pend = now
        if self.btn.down:
            if self.pend is not None and \
                    time.ticks_diff(now, self.pend) >= STEP_GRACE_MS:
                d = self._step()
                self.pend = None
                self.next_rep = time.ticks_add(now, STEP_HOLD_MS)
            elif self.next_rep is not None and \
                    time.ticks_diff(now, self.next_rep) >= 0:
                d = self._step()
                self.next_rep = time.ticks_add(now, self.rep_ms)
        else:
            if edge and self.pend is not None:
                d = self.delta  # tap released within the grace period
            self.pend = None
            self.next_rep = None
        return d


def setup_mode(disp, settings, btn_a, btn_b):
    """Adjust the MHz of the current turbo state. A+B saves and exits."""
    editing_turbo = settings.turbo or settings.mhz_normal is None
    val = settings.mhz_turbo if editing_turbo else settings.mhz_normal

    set_reset_mirror(False)  # no reset pulses while editing
    disp.show('SEt')
    while btn_a.down or btn_b.down:  # wait out the entry hold, else the
        btn_a.update()               # A+B-saves check below fires at once
        btn_b.update()
        time.sleep_ms(10)
    time.sleep_ms(300)
    disp.blink(1)  # 2 Hz hardware blink marks setup mode
    show_mhz(disp, val)

    step_a = Stepper(btn_a, +1)
    step_b = Stepper(btn_b, -1)
    while True:
        now = time.ticks_ms()
        edge_a = btn_a.update()
        edge_b = btn_b.update()
        if btn_a.down and btn_b.down:
            break  # save and leave
        d = step_a.poll(now, edge_a) + step_b.poll(now, edge_b)
        if d:
            idx = min(_IDX_MAX, max(1, _mhz_to_idx(val) + d))
            new = _idx_to_mhz(idx)
            if new != val:
                val = new
                show_mhz(disp, val)
        time.sleep_ms(10)

    if editing_turbo:
        settings.mhz_turbo = val
    else:
        settings.mhz_normal = val
    settings.save()
    disp.blink(0)

    while btn_a.down or btn_b.down:  # wait for release before resuming
        btn_a.update()
        btn_b.update()
        time.sleep_ms(10)
    set_reset_mirror(True)


# --- main ---------------------------------------------------------------

def run():
    global hdd_pulse

    settings = Settings()
    disp = SegmentDisplay(brightness=config.BRIGHTNESS)
    TURBO_OUT.value(settings.turbo)  # tell the motherboard first

    # Reset button passes straight through to GP20, by interrupt so it
    # tracks even while the boot delay or spin animation is running.
    _mirror_reset()
    BTN_RESET.irq(handler=_mirror_reset,
                  trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING)

    def show_speed():
        if settings.turbo or settings.mhz_normal is None:
            show_mhz(disp, settings.mhz_turbo)
        else:
            show_mhz(disp, settings.mhz_normal)

    def toggle_turbo():
        settings.turbo = not settings.turbo
        settings.save()
        TURBO_OUT.value(settings.turbo)
        disp.led(config.TURBO_LED, settings.turbo)
        if config.SPIN_ANIMATION and settings.mhz_normal is not None:
            spin(disp)
        show_speed()

    # Power-on: speed on the display, all LEDs lit for 2 seconds.
    show_speed()
    disp.leds(True, True, True)
    time.sleep(2)

    disp.leds(False, False, False)
    disp.led(config.POWER_LED, True)   # power LED stays on from here
    disp.led(config.TURBO_LED, settings.turbo)

    # Catch HDD pulses shorter than the polling interval, and normalize
    # the level shifter's power-on state (it may have latched garbage).
    HDD_IN.irq(handler=_hdd_irq, trigger=_HDD_TRIG)
    kick_hdd_line()

    btn_a = DebouncedPin(BTN_RESET)
    btn_b = DebouncedPin(BTN_TURBO)
    b_pend = None       # B press waiting out the combo grace window
    combo_since = None  # when both buttons became held
    egg_armed = False
    hdd_lit = False
    hdd_off_at = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        edge_a = btn_a.update()
        edge_b = btn_b.update()

        # --- A+B held -> setup mode ---------------------------------
        if btn_a.down and btn_b.down:
            b_pend = None
            egg_armed = False
            if combo_since is None:
                combo_since = now
            elif time.ticks_diff(now, combo_since) >= config.SETUP_HOLD_MS:
                combo_since = None
                setup_mode(disp, settings, btn_a, btn_b)
                show_speed()
                continue
        else:
            combo_since = None

        # --- button A: reset flash + easter egg ---------------------
        if edge_a and btn_a.down:
            egg_armed = True
            disp.show('---')
            time.sleep_ms(config.RESET_FLASH_MS)
            show_speed()
        if (egg_armed and btn_a.down and not btn_b.down
                and btn_a.held_ms() >= config.EGG_HOLD_MS):
            egg_armed = False
            easter_egg(disp)
            show_speed()

        # --- button B: turbo toggle, unless A+B is forming ----------
        if edge_b and btn_b.down and not btn_a.down:
            b_pend = now
        if b_pend is not None:
            if btn_a.down:
                b_pend = None  # combo forming, swallow the toggle
            elif not btn_b.down or \
                    time.ticks_diff(now, b_pend) >= COMBO_GRACE_MS:
                b_pend = None
                toggle_turbo()

        # --- HDD LED -------------------------------------------------
        if hdd_pulse:
            hdd_pulse = False
            hdd_off_at = time.ticks_add(now, config.HDD_MIN_ON_MS)
            if not hdd_lit:
                hdd_lit = True
                disp.led(config.HDD_LED, True)
        elif hdd_lit and time.ticks_diff(now, hdd_off_at) >= 0:
            kick_hdd_line()
            if hdd_active():  # motherboard is genuinely still driving
                hdd_off_at = time.ticks_add(now, config.HDD_MIN_ON_MS)
            else:
                hdd_lit = False
                disp.led(config.HDD_LED, False)

        time.sleep_ms(10)


run()
