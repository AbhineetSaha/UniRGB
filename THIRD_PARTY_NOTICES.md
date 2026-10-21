# Third-party notices

## Bundled with the installer

The Windows installer ships these components unmodified. The build checks each against a pinned SHA-256 hash
(`tools/fetch_pawnio.py`), and their licence texts are installed next to them in `{app}\pawnio`.

| Component | Licence | Source | Used for |
|---|---|---|---|
| PawnIO driver installer 2.2.0 | GPL-2.0 | [namazso/PawnIO](https://github.com/namazso/PawnIO) (tag 2.2.0) | Installed by the one-time setup, only if you turn on CPU temperature |
| PawnIO module `AMDFamily17.bin` 0.2.11 | LGPL-2.1 | [namazso/PawnIO.Modules](https://github.com/namazso/PawnIO.Modules) (release 0.2.11) | Loaded by the hardware helper to read the CPU temperature register |

## Sources of protocol facts

UniRGB's own code re-implements publicly documented protocols. No code was copied. The projects below are the
sources of those facts and are credited here and in each module's docstring.

| Source | Licence | Facts used | UniRGB module |
|---|---|---|---|
| [openrazer](https://github.com/openrazer/openrazer) | GPL-2.0-or-later | Razer HID report layout, CRC, command classes and IDs, Basilisk V3 Pro matrix size | `unirgb/protocols/razer.py` |
| [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) | GPL-2.0-or-later | MSI Mystic Light 761 report layout and tested board list; Evision V2 keyboard framing; Basilisk V3 Pro LED order; OpenRGB SDK network protocol | `unirgb/protocols/msi761.py`, `unirgb/protocols/evision_v2.py`, `unirgb/adapters/openrgb.py` |
| [AntEsports-Cooler-Controller](https://github.com/neonvarun/AntEsports-Cooler-Controller) | MIT | Pump-display report layout (5131:2007) | `unirgb/protocols/antcooler.py` |
| Linux `k10temp` driver | GPL-2.0 | AMD Zen temperature register (SMN 0x59800) and its encoding | `unirgb/hardware_helper.py` |
| Razer Chroma SDK REST documentation | Razer terms | REST endpoints and effect payloads | `unirgb/adapters/razer_chroma.py` |
| [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | MPL-2.0 | `data.json` web-server format | `unirgb/sensors.py` |

Optional programs that UniRGB can work with but does not ship are listed in [docs/open-source.md](docs/open-source.md).
