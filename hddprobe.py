"""HDD line probe: measure activity, pulse widths, and TXB latching
on every input in config.HDD_INPUTS at once.

Run while the PC generates disk activity (copy files, dir /s, defrag):

    tools/mpr run hddprobe.py

Stops main.py while it runs (about 15 s); restart the front panel with
    tools/mpr exec --no-follow "import main"
Every long active stretch is "kicked" the same way main.py does, which
tells apart a source genuinely holding the line from the TXB0104
latching it.  Results also land in :hddprobe.out in case USB drops.
"""

import time
from machine import Pin

try:  # follow the deployed config; fall back for older deployments
    from config import HDD_INPUTS
except ImportError:
    HDD_INPUTS = ((18, False, False),)

SAMPLE_MS = 15000
LATCH_CHECK_MS = 200  # active this long without a break -> kick and see
MAX_PULSES = 2000     # cap stored widths so memory stays flat


class Chan:
    def __init__(self, pin_no, active_low, direct=False):
        self.n = pin_no
        self.act = 0 if active_low else 1
        self.idle = 1 - self.act
        # pull only on direct GPIO lines; a pull on a TXB channel
        # fights its keeper and the line oscillates
        if direct:
            self.pull = Pin.PULL_UP if active_low else Pin.PULL_DOWN
        else:
            self.pull = None
        self.pin = Pin(pin_no, Pin.IN, self.pull)
        self.pulses = []
        self.gaps = []
        self.edges = 0
        self.active_us = 0
        self.kicks = self.latched = self.genuine = 0
        self.level = self.pin.value()
        now = time.ticks_us()
        self.t_edge = now
        self.t_check = now

    def kick(self):
        self.pin.init(Pin.OUT, value=self.idle)
        time.sleep_us(20)
        self.pin.init(Pin.IN, self.pull)
        time.sleep_us(50)

    def sample(self, now):
        v = self.pin.value()
        if v != self.level:
            width = time.ticks_diff(now, self.t_edge)
            if self.level == self.act:
                self.active_us += width
                if len(self.pulses) < MAX_PULSES:
                    self.pulses.append(width)
            elif len(self.gaps) < MAX_PULSES:
                self.gaps.append(width)
            self.level = v
            self.t_edge = now
            self.t_check = now
            self.edges += 1
        elif (self.level == self.act
              and time.ticks_diff(now, self.t_check) > LATCH_CHECK_MS * 1000):
            self.kicks += 1
            self.kick()
            if self.pin.value() == self.act:
                self.genuine += 1   # source really is holding it
                self.t_check = now  # don't re-kick for another window
            else:
                self.latched += 1
                # treat like a release edge the TXB swallowed
                self.active_us += time.ticks_diff(now, self.t_edge)
                if len(self.pulses) < MAX_PULSES:
                    self.pulses.append(time.ticks_diff(now, self.t_edge))
                self.level = self.idle
                self.t_edge = now
                self.t_check = now

    def report(self, total_us):
        lines = ['--- GP%d (active %s) ---'
                 % (self.n, 'LOW' if self.act == 0 else 'HIGH'),
                 'edges seen:        %d' % self.edges,
                 'duty cycle:        %.1f%% active'
                 % (100.0 * self.active_us / total_us),
                 'completed pulses:  %d' % len(self.pulses)]
        if self.pulses:
            p = sorted(self.pulses)
            lines.append('pulse width us:    min %d  med %d  max %d'
                         % (p[0], p[len(p) // 2], p[-1]))
        if self.gaps:
            g = sorted(self.gaps)
            lines.append('idle gap us:       min %d  med %d  max %d'
                         % (g[0], g[len(g) // 2], g[-1]))
        lines.append('long-active kicks: %d  (genuine hold: %d, TXB latch: %d)'
                     % (self.kicks, self.genuine, self.latched))
        return lines


def main():
    chans = [Chan(*entry) for entry in HDD_INPUTS]
    t_end = time.ticks_add(time.ticks_ms(), SAMPLE_MS)
    print('sampling %s for %d s, generate disk activity now...'
          % (', '.join('GP%d' % c.n for c in chans), SAMPLE_MS // 1000))
    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        now = time.ticks_us()
        for c in chans:
            c.sample(now)

    total_us = SAMPLE_MS * 1000
    lines = []
    for c in chans:
        lines.extend(c.report(total_us))
    report = '\n'.join(lines)
    print(report)
    # survive a USB dropout mid-run: results also land on flash
    with open('hddprobe.out', 'w') as f:
        f.write(report + '\n')


main()
