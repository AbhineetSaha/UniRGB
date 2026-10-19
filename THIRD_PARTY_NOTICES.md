# Third-party notices

UniRGB contains no third-party code. It re-implements publicly documented device protocols. The
projects below are the sources of those facts. They are credited here and in each module's docstring.

| Source | Licence | Facts used | UniRGB module |
|---|---|---|---|
| [openrazer](https://github.com/openrazer/openrazer) | GPL-2.0-or-later | Razer HID report layout, CRC, command classes/IDs, Basilisk V3 Pro matrix size | `unirgb/protocols/razer.py` |
| [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) | GPL-2.0-or-later | MSI Mystic Light 761 report layout and tested board list; Evision V2 keyboard framing; Basilisk V3 Pro LED order; OpenRGB SDK network protocol | `unirgb/protocols/msi761.py`, `unirgb/protocols/evision_v2.py`, `unirgb/adapters/openrgb.py` |
| [AntEsports-Cooler-Controller](https://github.com/neonvarun/AntEsports-Cooler-Controller) | MIT | Pump-display report layout (5131:2007) | `unirgb/protocols/antcooler.py` |
| Razer Chroma SDK REST documentation | Razer terms | REST endpoints and effect payloads | `unirgb/adapters/razer_chroma.py` |
| [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | MPL-2.0 | `data.json` web-server format | `unirgb/sensors.py` |

Optional external programs (not distributed with UniRGB) are listed in `docs/open-source.md`.
