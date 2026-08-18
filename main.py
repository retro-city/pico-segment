# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Retro PC front panel controller, runs at boot.

Behavior:
  - Display shows the CPU speed: mhz_turbo while turbo is on,
    mhz_normal while it is off. Speeds and turbo state persist in
    settings.json; config.py supplies first-boot defaults.
  - All three LEDs light for 2 s at power-on, then only the power LED
    stays lit. If a boot.wav is on the filesystem it plays through the
    piezo meanwhile (see bootsound.py).
  - Button B (SW2, GP7) toggles turbo when released: turbo LED follows,
    GP20 (5 V on J3 pin 3) drives the motherboard (high = turbo on),
    state is saved, and the speed change plays a spin animation. Hold B
    alone for CLICK_MUTE_HOLD_MS instead to mute/unmute the HDD
    clicker (saved too); the display scrolls HDCLIC ON / HDCLIC OFF.
  - Button A (SW1, GP8) is the reset button, mirrored to GP21 (5 V on
    J3 pin 1) with config polarity; the display flashes ---.
    Hold A alone for a second for a surprise: a spell of faked drive
    activity (HDD LED and clicker), then the scrolling text.
  - J1 (button C, GP6) is a maintained keyboard-lock switch: GP19
    (5 V on J3 pin 5) follows its position with config polarity, and
    the display reads LOC instead of the speed while it is locked.
  - Hold A+B for SETUP_HOLD_MS to enter setup: the speed for the
    current turbo state blinks; B = +1 MHz, A = -1 MHz (hold to
    repeat), A+B together saves and exits. The reset output to the
    motherboard is suspended while setup is open.
  - A passive piezo on CLICK_PIN clicks while the HDD LED is lit, so
    the silent CF card still sounds like a mechanical drive seeking.
  - The HDD LED mirrors activity on every input in config.HDD_INPUTS:
    direct GPIO lines by edge IRQ, TXB-backed lines by polling only —
    the TXB latches the active level until it is kicked back to idle,
    so even microsecond pulses wait around for the poll.
"""

import time
from machine import Pin

import bootsound
import config
from ht16k33_seg import SegmentDisplay
from prefs import Settings, usb_host_present

BTN_TURBO = Pin(7, Pin.IN)   # SW2 / BUTT-B, active low, external pull-up
BTN_RESET = Pin(8, Pin.IN)   # SW1 / BUTT-A, active low, external pull-up
BTN_LOCK = Pin(6, Pin.IN)    # J1 / BUTT-C, active low, external pull-up
# HDD activity inputs are built in the HDD section below (HDD_LINES)
TURBO_OUT = Pin(config.TURBO_OUT_PIN, Pin.OUT)
RESET_OUT = Pin(config.RESET_OUT_PIN, Pin.OUT)
LOCK_OUT = Pin(config.LOCK_OUT_PIN, Pin.OUT)

STEP_GRACE_MS = 150    # setup: tell a +-1 step apart from an A+B save
STEP_HOLD_MS = 450     # setup: hold this long before auto-repeat
STEP_REPEAT_MS = 80    # setup: auto-repeat interval for +-1 steps
BIG_STEP_HOLD_MS = 2000  # setup: hold this long and steps become +-10
BIG_STEP_REPEAT_MS = 240  # setup: slower auto-repeat while stepping +-10

# The adjustable speed runs on a display grid: 1 MHz steps up to 999,
# then 10 MHz steps shown as GHz with two decimals (1.00 ... 9.99).
from prefs import MHZ_MAX
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
    """Enable/disable the button-A -> GP21 mirror (off during setup)."""
    global _reset_mirror_on
    _reset_mirror_on = enabled
    if enabled:
        _mirror_reset()
    else:
        RESET_OUT.value(0 if config.RESET_ACTIVE_HIGH else 1)  # inactive


# --- keyboard lock ------------------------------------------------------

locked = False  # last known position of the maintained J1 switch


def lock_engaged(low):
    """True when the maintained J1 switch sits in the locked position.

    `low` is the debounced pin level, True meaning the contact is
    closed to ground.
    """
    return low if config.LOCK_SWITCH_ACTIVE_LOW else not low


def set_lock_out(is_locked):
    """Drive the lock output, and remember it for the display."""
    global locked
    locked = is_locked
    LOCK_OUT.value(is_locked if config.LOCK_ACTIVE_HIGH else not is_locked)


# --- HDD activity inputs -----------------------------------------------

hdd_pulse = False


def _hdd_irq(pin):
    global hdd_pulse
    hdd_pulse = True
    # Disarm until the LED turns off again: a noisy/toggling line can
    # otherwise fire IRQs faster than the loop runs and starve the
    # buttons. IRQs only ever LIGHT the LED; polling keeps it lit.
    pin.irq(handler=None)


class HddLine:
    """One activity input; any line reading active lights the LED."""

    def __init__(self, pin_no, active_low, direct=False):
        self.active_low = active_low
        self.direct = direct
        self.trig = Pin.IRQ_FALLING if active_low else Pin.IRQ_RISING
        # Only direct GPIO lines get an idle-bias pull (so a
        # disconnected line reads "no activity" instead of floating)
        # and edge IRQs. TXB-backed lines get neither: a pull fights
        # the channel's keeper, and a slow edge (an opto turning on)
        # makes its one-shots oscillate — with an IRQ armed, that
        # oscillation fires at C level faster than the handler can
        # disarm it and hangs the board. Polling misses nothing there,
        # because the TXB latches the active level until kicked.
        if direct:
            self.pull = Pin.PULL_UP if active_low else Pin.PULL_DOWN
        else:
            self.pull = None
        self.pin = Pin(pin_no, Pin.IN, self.pull)
        self.pin.irq(handler=None)  # shed any handler from a soft restart

    def arm(self):
        if self.direct:
            self.pin.irq(handler=_hdd_irq, trigger=self.trig)

    def active(self):
        return self.pin.value() == (0 if self.active_low else 1)

    def kick(self):
        """Re-arm after the source releases the line.

        A source that only drives the active level leaves the TXB
        latched, so the line would read active forever. Briefly driving
        the idle level from this side resets it; a genuinely driven
        line overpowers the pulse and reads active again immediately.
        Harmless no-op for the direct-GPIO loom.
        """
        self.pin.init(Pin.OUT, value=1 if self.active_low else 0)
        time.sleep_us(20)
        self.pin.init(Pin.IN, self.pull)
        time.sleep_us(50)  # let the line settle before it is read again


HDD_LINES = [HddLine(*entry) for entry in config.HDD_INPUTS]


def arm_hdd_lines():
    for line in HDD_LINES:
        line.arm()


def hdd_active():
    return any(line.active() for line in HDD_LINES)


def kick_hdd_line():
    for line in HDD_LINES:
        line.kick()


# --- HDD clicker --------------------------------------------------------

class Clicker:
    """Piezo clicks standing in for a mechanical drive's seek noise.

    No tone. A piezo disc clicks on a voltage EDGE -- it flexes once and
    rings down at its own resonance -- and a plain DC step is exactly
    what the hardware HDD clickers feed theirs. A seek here is two
    edges: one when the head 'moves', another CLICK_HOLD_MS later when
    it 'lands', which reads as the tick-tock of a real actuator. Driving
    a tone instead gives a beep, however short.

    Nothing blocks. tick() flips the line and books the second edge;
    service() delivers it from the main loop, whose 10 ms period adds a
    little jitter that only helps. With CLICK_PIN_B set the piezo sits
    between two pins driven in antiphase, so every edge swings twice
    the supply -- the cheap way to make it louder. Disabled, or with no
    piezo fitted, the class is inert.
    """

    def __init__(self, settings):
        self.s = settings                # click_hold_ms, click_gap_ms, clicker
        self.pin_a = None
        self.pin_b = None
        self.next_at = time.ticks_ms()   # earliest next seek
        self.release_at = None           # when the pending second edge lands
        self._pol = 0
        self._i = 0
        if config.CLICK_ENABLED:
            self.pin_a = Pin(config.CLICK_PIN, Pin.OUT, value=0)
            bootsound.stiff_pad(config.CLICK_PIN)
            if config.CLICK_PIN_B is not None:
                self.pin_b = Pin(config.CLICK_PIN_B, Pin.OUT, value=1)
                bootsound.stiff_pad(config.CLICK_PIN_B)

    @property
    def muted(self):
        return not self.s.clicker

    def _edge(self):
        # Every edge reverses the voltage across the piezo. Single-ended
        # that is 0 <-> 3V3; push-pull it is +3V3 <-> -3V3.
        self._pol ^= 1
        self.pin_a.value(self._pol)
        if self.pin_b is not None:
            self.pin_b.value(self._pol ^ 1)

    def tick(self, now, force=False):
        """Start a seek, unless the previous one was too recent.

        `force` skips the rate limit, for callers that already decide
        their own spacing (the drive burst in the easter egg).
        """
        if self.pin_a is None or self.muted:
            return
        if not force and time.ticks_diff(now, self.next_at) < 0:
            return
        self._edge()  # head moves
        holds = self.s.click_hold_ms
        self.release_at = time.ticks_add(now, holds[self._i % len(holds)])
        self._i += 1  # walk the hold table so seeks are not all alike
        self.next_at = time.ticks_add(now, self.s.click_gap_ms)

    def service(self, now):
        """Deliver the pending second edge once due. Call every loop."""
        if self.release_at is not None and \
                time.ticks_diff(now, self.release_at) >= 0:
            self.release_at = None
            self._edge()  # head lands

    def pending(self):
        return self.release_at is not None


def hdd_burst(disp, clicker):
    """Fake a spell of drive activity, for the easter egg.

    Flashes the HDD LED and clicks along with it, in uneven bursts so it
    reads as a drive working rather than a blinking light. Blocking, so
    it services the clicker itself; the caller owns the LED afterwards.
    """
    on = config.HDD_BURST_ON_MS
    off = config.HDD_BURST_OFF_MS
    for i in range(config.HDD_BURST_PULSES):
        disp.led(config.HDD_LED, True)
        clicker.tick(time.ticks_ms(), force=True)  # one seek per flash
        time.sleep_ms(on[i % len(on)])
        clicker.service(time.ticks_ms())
        disp.led(config.HDD_LED, False)
        time.sleep_ms(off[i % len(off)])
        clicker.service(time.ticks_ms())
    while clicker.pending():  # let the last seek land before moving on
        time.sleep_ms(5)
        clicker.service(time.ticks_ms())


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


def easter_egg(disp, clicker, text):
    """The drive 'loads' the message: seek burst first, then the text."""
    spin(disp)
    hdd_burst(disp, clicker)
    disp.scroll(text, config.EGG_SCROLL_MS)
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

    # B (SW2) is the right-hand button, so it counts up; A counts down.
    step_a = Stepper(btn_a, -1)
    step_b = Stepper(btn_b, +1)
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
    disp.blink(0)
    if not settings.save():
        disp.show(config.USB_TEXT)   # PC owns the drive: kept in RAM only
        time.sleep_ms(config.USB_FLASH_MS)

    while btn_a.down or btn_b.down:  # wait for release before resuming
        btn_a.update()
        btn_b.update()
        time.sleep_ms(10)
    set_reset_mirror(True)


# --- main ---------------------------------------------------------------

def run():
    global hdd_pulse

    settings = Settings()   # boot.py has already seeded settings.json
    disp = SegmentDisplay(brightness=settings.brightness)
    TURBO_OUT.value(settings.turbo)  # tell the motherboard first
    set_lock_out(lock_engaged(BTN_LOCK.value() == 0))

    # Reset button passes straight through to GP21, by interrupt so it
    # tracks even while the boot delay or spin animation is running.
    _mirror_reset()
    BTN_RESET.irq(handler=_mirror_reset,
                  trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING)

    def show_speed():
        if locked:
            disp.show(config.LOCK_TEXT)  # the lock has no LED of its own
        elif settings.turbo or settings.mhz_normal is None:
            show_mhz(disp, settings.mhz_turbo)
        else:
            show_mhz(disp, settings.mhz_normal)

    def save_settings():
        # A deferred save (PC owns the drive) is worth telling the user
        # about, since the change will not survive a power cycle.
        if not settings.save():
            disp.show(config.USB_TEXT)
            time.sleep_ms(config.USB_FLASH_MS)

    def toggle_turbo():
        settings.turbo = not settings.turbo
        save_settings()
        TURBO_OUT.value(settings.turbo)
        disp.led(config.TURBO_LED, settings.turbo)
        if settings.spin_animation and settings.mhz_normal is not None:
            spin(disp)
        show_speed()

    # Power-on: speed on the display, all LEDs lit for 2 seconds, and
    # the boot sound (if a file is there) playing over the top -- it
    # runs on PIO/DMA, so the lamp test does not wait for it.
    snd = None
    if settings.boot_sound and config.CLICK_ENABLED:
        snd = bootsound.play(settings.boot_sound, config.BOOT_SOUND_MAX_KB * 1024,
                             config.CLICK_PIN, config.CLICK_PIN_B)
    show_speed()
    disp.leds(True, True, True)
    time.sleep(2)

    disp.leds(False, False, False)
    disp.led(config.POWER_LED, True)   # power LED stays on from here
    disp.led(config.TURBO_LED, settings.turbo)

    # Normalize the level shifter's power-on state (it may have latched
    # garbage), then listen for the first pulse.
    kick_hdd_line()
    arm_hdd_lines()

    if snd is not None:
        snd.wait()   # a sound longer than the lamp test finishes here
        snd.stop()   # ...and hands the piezo pins to the clicker
    clicker = Clicker(settings)

    def toggle_clicker():
        settings.clicker = not settings.clicker   # the clicker reads it live
        save_settings()
        disp.scroll(config.CLICK_TEXT_ON if settings.clicker
                    else config.CLICK_TEXT_OFF, config.CLICK_TEXT_SCROLL_MS)
        show_speed()

    def apply_settings():
        # The host edited settings.json: make the panel match it. The
        # clicker and HDD timings are read live; boot_sound at next boot.
        TURBO_OUT.value(settings.turbo)
        disp.led(config.TURBO_LED, settings.turbo)
        disp.brightness(settings.brightness)
        show_speed()

    btn_a = DebouncedPin(BTN_RESET)
    btn_b = DebouncedPin(BTN_TURBO)
    btn_c = DebouncedPin(BTN_LOCK)
    host_was = usb_host_present()
    b_pend = False      # B is down, turbo toggles when it comes back up
    mute_armed = False  # this B press can still become a mute toggle
    combo_since = None  # when both buttons became held
    egg_armed = False
    hdd_lit = False
    hdd_off_at = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        edge_a = btn_a.update()
        edge_b = btn_b.update()

        # --- USB drive: the PC has just let go ----------------------
        # Re-read the filesystem the host may have written to, adopt an
        # edited settings.json, or flush changes made while it was here.
        host = usb_host_present()
        if host_was and not host:
            if settings.sync():
                apply_settings()
        host_was = host

        # --- A+B held -> setup mode ---------------------------------
        if btn_a.down and btn_b.down:
            b_pend = False
            mute_armed = False
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
            easter_egg(disp, clicker, settings.egg_text)
            disp.led(config.HDD_LED, hdd_lit)  # the burst borrowed the LED
            show_speed()

        # --- button B: turbo on release, clicker mute on a long hold --
        # The toggle waits for the release rather than firing partway
        # through the press, so a long hold can claim the press for the
        # mute instead of flipping the speed on its way there.
        if edge_b and btn_b.down and not btn_a.down:
            b_pend = True
            mute_armed = True
        if b_pend:
            if btn_a.down:
                b_pend = False      # combo forming, swallow the toggle
                mute_armed = False
            elif not btn_b.down:
                b_pend = False
                toggle_turbo()
        if (mute_armed and btn_b.down and not btn_a.down
                and btn_b.held_ms() >= config.CLICK_MUTE_HOLD_MS):
            mute_armed = False
            b_pend = False          # a long hold is not a turbo tap
            toggle_clicker()

        # --- J1: keyboard lock follows the maintained switch --------
        # Debounced rather than mirrored by IRQ, so the contact's
        # bounce does not chatter the opto on every throw.
        if btn_c.update():
            set_lock_out(lock_engaged(btn_c.down))
            show_speed()  # LOC while locked, the speed again once released

        # --- HDD LED -------------------------------------------------
        # Direct lines report by IRQ (which disarms itself until the
        # LED is dark again); TXB lines are picked up by the dark-state
        # poll, their latch holding the pulse until it is seen. While
        # lit the raw level is NOT trusted — a latched line reads
        # active forever — so the kick at timeout decides between a
        # genuine hold and a stale latch.
        if hdd_pulse or (not hdd_lit and hdd_active()):
            hdd_pulse = False
            hdd_off_at = time.ticks_add(now, settings.hdd_min_on_ms)
            if not hdd_lit:
                hdd_lit = True
                disp.led(config.HDD_LED, True)
        elif hdd_lit and time.ticks_diff(now, hdd_off_at) >= 0:
            kick_hdd_line()
            if hdd_active():  # source is genuinely still driving
                hdd_off_at = time.ticks_add(now, settings.hdd_min_on_ms)
            else:
                hdd_lit = False
                disp.led(config.HDD_LED, False)
                arm_hdd_lines()  # dark again — listen for the next burst

        # Seek for as long as the LED is lit; the clicker rate-limits
        # itself, so one short access clicks once and a long transfer
        # chatters. service() lands the second edge of each seek, so it
        # runs every pass, lit or not.
        if hdd_lit:
            clicker.tick(now)
        clicker.service(now)

        time.sleep_ms(10)


run()
