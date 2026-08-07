# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Board verification: light every wired LED element one at a time.

Run from the host with:  tools/mpr run segtest.py
Watch the board and check that each printed element matches what lights
up. Any mismatch means the driver's COM/ROW map disagrees with the
hardware. Ends with everything on for two seconds, then a clear.
"""

import time
from ht16k33_seg import SegmentDisplay

SEG_NAMES = ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'DP')
LED_NAMES = {8: 'red (LED2)', 9: 'yellow (LED3)', 10: 'green (LED4)'}

ELEMENTS = [(com, row, 'DIG%d segment %s' % (com + 1, SEG_NAMES[row]))
            for com in range(3) for row in range(8)]
ELEMENTS += [(3, row, 'status LED %s' % name) for row, name in LED_NAMES.items()]

disp = SegmentDisplay()

for com, row, name in ELEMENTS:
    for i in range(len(disp.buf)):
        disp.buf[i] = 0
    disp.buf[2 * com + row // 8] = 1 << (row % 8)
    disp.update()
    print('COM%d ROW%-2d -> %s' % (com, row, name))
    time.sleep_ms(350)

print('All elements on')
for com, row, _ in ELEMENTS:
    disp.buf[2 * com + row // 8] |= 1 << (row % 8)
disp.update()
time.sleep(2)
disp.clear()
print('Done')
