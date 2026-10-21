"""Opt-in RAM lighting helper (option 2): SMBus access through the PawnIO driver.

Kept outside the `unirgb` package on purpose: the main app never touches the SMBus and
tests/test_safety.py keeps enforcing that. This package needs administrator rights and
the PawnIO driver, and is only ever run when the user starts it explicitly.

Phase 1 is read-only: there is no write path in this package (tests/test_smbus.py).

SPDX-License-Identifier: GPL-3.0-or-later
"""
