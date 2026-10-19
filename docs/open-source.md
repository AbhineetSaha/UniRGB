# Open-source readiness: decisions

Goal: anyone can download, run, fork and redistribute UniRGB without depending on, or shipping,
proprietary software.

## Licence: GPL-3.0-or-later

| Option | Why not / why |
|---|---|
| MIT / Apache-2.0 | Simplest for adoption, but UniRGB re-implements protocol facts published by GPL projects (openrazer, OpenRGB). Facts are not copyrightable, but a permissive licence invites questions from those communities |
| **GPL-3.0-or-later** | Compatible with the GPL-2.0-or-later projects UniRGB learned from, keeps forks open, standard in the PC-lighting world (OpenRGB is GPL). **Chosen** |

No code was copied from any project. Each protocol module names its sources in its docstring.

## Third-party software: never bundled

| Software | Licence | How UniRGB uses it | Shipped? |
|---|---|---|---|
| OpenRGB | GPL-2.0-or-later | Separate program, reached over its documented network SDK (TCP 6742). Used only for RAM lighting | No, the user installs it |
| PawnIO | open source, signed binaries | Kernel driver used **by OpenRGB / LibreHardwareMonitor**, not by UniRGB | No |
| LibreHardwareMonitor | MPL-2.0 | Separate program. UniRGB reads its local web server (`/data.json`) for CPU temperature and fan speeds | No |
| Razer Chroma SDK | proprietary | Optional fallback adapter, called over its local REST API if Synapse is installed | No (part of Synapse) |
| AMD Ryzen Master SDK | **proprietary, redistribution forbidden** | Optional, off unless the user clicks "Use AMD Ryzen Master instead". Never the default | No |
| nvidia-smi | proprietary (part of the NVIDIA driver) | Optional GPU-temperature fallback, run as a separate process | No |
| Microsoft Edge | proprietary (ships with Windows) | Optional window host (`--app`). Any browser works at `http://127.0.0.1:47821` | No |

UniRGB itself depends only on the Python standard library.

## PC-specific assumptions removed

| Was | Now |
|---|---|
| USB 5131:2007 treated as the author's Ant Esports cooler | Generic chip also used by relay boards. **Nothing is sent until the user confirms it** in the UI (`confirmed` setting) |
| Keyboard always named "Kreo Hive RGB" | Name taken from the device's own USB product string |
| Inventory notes about "this PC" | Generic notes |
| CPU temperature via AMD's proprietary SDK by default | LibreHardwareMonitor (open source) by default. AMD is opt-in |
| `docs/system-inventory.md` | Kept as the **reference machine** the adapters were verified on |

## Safety rules kept for everyone

- Writes only to devices with a verified protocol and an exact VID/PID (and for MSI, a tested board ID).
- Live/volatile writes where possible (Razer NOSTORE, Kreo dynamic colors, MSI baseline restore).
- No SMBus, I²C, EC or firmware code in UniRGB (`tests/test_safety.py`).

## Before publishing

1. Create a public Git repository from a normal folder (not the session folder).
2. Keep `__pycache__/`, logs and `*.bin` out (`.gitignore` does this). Personal runtime data lives in
   `%APPDATA%\UniRGB` and `%LOCALAPPDATA%\UniRGB`, never in the repo.
3. Add the contributor flow (`CONTRIBUTING.md`): new boards and devices need a read-only probe log and a
   real-hardware test before their `Support` level can be raised.
