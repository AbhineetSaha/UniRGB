# UniRGB

One open-source app for your PC's lighting and peripherals. It controls the devices it has a verified
protocol for, directly and without vendor software, and tells you plainly which devices it can't control and why.

License: **GPL-3.0-or-later** · Windows 10/11 · Python 3.11+ · standard library only, no admin rights needed.

## Supported devices

| Device | What works | How |
|---|---|---|
| Razer Basilisk V3 Pro (1532:00AA / 00AB) | Color, zones (experimental), hardware brightness with read-back, DPI, DPI stages, polling rate, sleep timer, battery | Direct HID (protocol from openrazer). Lighting is never written to the mouse's saved profile |
| MSI Mystic Light 761 boards (0DB0:0076), tested: X870E GAMING PLUS WIFI (MS-7E70) | ARGB/EZ Conn headers per zone, setup read-back, baseline restore | Direct HID (protocol from OpenRGB). Blocked while MSI Center lighting runs |
| Kreo Hive RGB and other Evision V2 keyboards (320F:5055) | Whole-keyboard color, off | Direct HID live colors only. The keyboard reverts by itself when UniRGB stops |
| Ant Esports AIO pump display (5131:2007) | CPU (or GPU) temperature, °C/°F, anti-blink | HID output reports. **Sends nothing until you confirm** the device is your cooler (this chip is also used by relay boards) |
| RAM, and anything else OpenRGB supports | Color through OpenRGB | Optional: run OpenRGB with its SDK server. UniRGB uses it **for RAM only** |
| Razer Chroma devices | Color through Razer's Chroma SDK | Optional fallback if Synapse is installed |
| Everything else | Listed with the reason it isn't controllable | Read-only inventory |

Full evidence: [docs/device-capability-matrix.md](docs/device-capability-matrix.md).

## Run

```bash
python -m unirgb
```

Or double-click `UniRGB.cmd`. The UI opens at `http://127.0.0.1:47821/` (in an Edge app window if available).
**Quit** hands every device back to its own stored lighting. Options: `--no-direct`, `--simulate`, `--no-window`, `--port N`.

## Optional companions (open source, installed separately)

- **LibreHardwareMonitor**: CPU temperature for the pump display, plus fan speeds. Run it as administrator
  and enable *Options → Remote Web Server* (port 8085).
- **OpenRGB**: RAM lighting. Run it as administrator, untick devices UniRGB already drives (Settings → Supported
  Devices), and start the SDK server (port 6742).

UniRGB never bundles third-party or proprietary software. See [docs/open-source.md](docs/open-source.md).

## Safety

- Writes only to exact, verified devices. Volatile writes wherever the device allows it.
- No SMBus, I²C, EC or firmware code in UniRGB (enforced by a test).
- Restore paths for every writable device. `tools/` has scripts to stop or restore vendor lighting services.

Details: [docs/security-and-safety.md](docs/security-and-safety.md) · [docs/direct-control.md](docs/direct-control.md).

## Develop

```bash
python -m unittest discover -s tests -t .
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before adding a device. Architecture: [docs/architecture.md](docs/architecture.md) ·
decisions: [docs/architecture-decisions.md](docs/architecture-decisions.md) · sources: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
