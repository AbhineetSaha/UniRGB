# Licensing and third-party software

Goal: anyone can download, run, fork and redistribute UniRGB without depending on, or shipping, proprietary software.

## Licence: GPL-3.0-or-later

| Option | Why not / why |
|---|---|
| MIT / Apache-2.0 | Simplest for adoption, but UniRGB re-implements protocol facts published by GPL projects (openrazer, OpenRGB). Facts are not copyrightable, but a permissive licence invites questions from those communities |
| **GPL-3.0-or-later** | Compatible with the GPL-2.0-or-later projects UniRGB learned from, keeps forks open, and standard for PC-lighting software (OpenRGB is GPL). **Chosen** |

No code was copied from any project. Each protocol module names its sources in its docstring.

## Third-party software

| Software | Licence | How UniRGB uses it | Shipped? |
|---|---|---|---|
| PawnIO driver 2.2.0 | GPL-2.0 | Official signed installer, run by the one-time setup only if you turn on CPU temperature or RAM lighting | **Yes**, unmodified, SHA-256 pinned in `tools/fetch_pawnio.py` |
| PawnIO module `AMDFamily17.bin` 0.2.11 | LGPL-2.1 | Loaded by UniRGB's hardware helper to read the CPU temperature register | **Yes**, unmodified, SHA-256 pinned |
| PawnIO module `SmbusPIIX4.bin` 0.2.11 | LGPL-2.1 | Loaded by UniRGB's hardware helper to reach RAM lighting controllers on AMD's SMBus | **Yes**, unmodified, SHA-256 pinned |
| OpenRGB | GPL-2.0-or-later | Separate program, reached over its documented network SDK (TCP 6742). Used for RAM lighting only | No |
| LibreHardwareMonitor | MPL-2.0 | Separate program. UniRGB reads its local web server (`/data.json`) for fan speeds and, as a fallback, CPU temperature | No |
| Razer Chroma SDK | proprietary | Optional fallback adapter, called over its local REST API if Synapse is installed | No (part of Synapse) |
| AMD Ryzen Master SDK | proprietary, redistribution forbidden | Optional, only if you click "Use AMD Ryzen Master instead" on the pump display | No |
| nvidia-smi | proprietary (part of the NVIDIA driver) | GPU temperature fallback, run as a separate process | No |
| Microsoft Edge | proprietary (ships with Windows) | Optional window host (`--app`). Any browser works at `http://127.0.0.1:47821` | No |

UniRGB's own code depends only on the Python standard library.

## Rules that keep it portable

| Rule | Why |
|---|---|
| Nothing is sent to the 5131:2007 chip until the user confirms it is their cooler display | The same generic chip is used by relay boards and other gadgets |
| Device names come from the device's own USB strings | Avoids naming hardware after one specific product |
| CPU temperature uses open-source paths by default (PawnIO, LibreHardwareMonitor). AMD's SDK is opt-in | No proprietary dependency by default |
| Writes only to exact VID:PID matches and, for motherboards, tested board IDs | Protects similar-looking hardware |
| Personal data lives in `%APPDATA%\UniRGB` and `%LOCALAPPDATA%\UniRGB`, never in the repository | Safe to fork and share |
