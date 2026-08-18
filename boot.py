# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Vidar Waagbø
"""Runs before USB comes up; see seed.py for what and why."""
try:
    import seed
    seed.seed()
except Exception as e:      # boot must never fail over the drive's contents
    print('boot: seed failed:', e)
