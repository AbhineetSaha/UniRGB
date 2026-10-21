# UniRGB

One open-source app for your PC's lighting. UniRGB talks to supported devices directly, without their vendor apps,
and tells you plainly which devices it can't control and why.

License: **GPL-3.0-or-later** · Windows 10/11 · written in Python (standard library only)

## Supported devices

| Device | What works | How |
|---|---|---|
| Razer Basilisk V3 Pro (1532:00AA wired, 1532:00AB HyperSpeed) | Color, zones (experimental), hardware brightness with read-back, DPI and DPI stages, polling rate, sleep timer, battery | Direct HID. Lighting is never written to the mouse's saved profile |
| MSI Mystic Light 761 controller (0DB0:0076) on tested boards (MS-7E70: X870E GAMING PLUS WIFI) | ARGB and EZ Conn headers per zone, setup read-back, restore of the original setup | Direct HID. Blocked while MSI Center's lighting runs |
| Kreo Hive RGB and other Evision V2 keyboards (320F:5055) | Whole-keyboard color, off | Direct HID, live colors only. The keyboard returns to its stored lighting by itself when UniRGB stops |
| Ant Esports AIO pump display (5131:2007) | CPU or GPU temperature, °C/°F, no flashing above 84 °C | HID output reports. **Sends nothing until you confirm** the device is your cooler, because other gadgets use the same chip |
| RAM with ENE controllers (for example G.Skill DDR5) on AMD boards | Color per stick, off | Through UniRGB's hardware helper, after you turn on RAM lighting. Colors are never saved to the sticks. OpenRGB also works if you run it |
| Razer Chroma devices | Color through Razer's Chroma SDK | Fallback when Razer Synapse is installed |
| Everything else | Listed with the reason it isn't controllable | Read-only inventory |

Details and evidence: [docs/device-capability-matrix.md](docs/device-capability-matrix.md). Missing your device?
[Open a device-support request](https://github.com/AbhineetSaha/UniRGB/issues/new/choose).

## Install

Download `UniRGB-Setup-<version>.exe` from the [latest release](https://github.com/AbhineetSaha/UniRGB/releases/latest)
and run it. The installer needs no administrator rights. The release is not code-signed yet, so Windows SmartScreen
may warn you: choose **More info → Run anyway**. Each release lists SHA-256 checksums you can verify.

## First start

UniRGB asks which features you want:

- **Lighting** for the devices above always works, with no driver and no admin rights.
- **CPU temperature on the pump display** needs the PawnIO driver. If you tick it, UniRGB asks for administrator
  rights **once** to install PawnIO (bundled with UniRGB) and a small background helper. Later starts need no prompt.
  You can turn it off again in **Settings**, which removes the helper.
- **RAM lighting** also needs PawnIO and the helper (the same one-time prompt). Each stick then appears as its own
  device. Colors are live only: quitting UniRGB, or a full power-off, returns the sticks to their own effect.

UniRGB runs in the background. Its icon sits in the notification area (the ^ arrow next to the clock): click it to
open the window, right-click for **Quit**. Quitting hands every device back to its own stored lighting.

## Troubleshooting

| You see | Do this |
|---|---|
| Razer mouse shows **Asleep** | The mouse sleeps after its sleep timer. Move it: UniRGB reconnects and puts your lighting back within about 15 s |
| "Razer Synapse is controlling this mouse's lighting" | Synapse is running a lighting effect and UniRGB's commands can't get through. Click **Quit Razer Synapse**, and disable *RazerAppEngine* in Task Manager → Startup apps so it doesn't come back |
| MSI board writes are blocked | MSI Center's lighting service is running. See [Turning on MSI direct control](docs/direct-control.md#turning-on-msi-direct-control) |
| Pump display shows the GPU temperature | Turn on **CPU temperature** in Settings, or start LibreHardwareMonitor with its web server enabled |
| "UniRGB hardware helper not answering" | Open **Settings** and run the setup again (one admin prompt) |

## Run from source

```bash
python -m unirgb
```

Python 3.11 or newer, no packages to install. The UI opens at `http://127.0.0.1:47821/` (in an Edge app window if
available). Options: `--no-window`, `--simulate` (adds clearly labelled fake devices), `--no-direct` (vendor APIs
only), `--port N`, `--verbose`. The one-time driver setup only works in the packaged app, not from source.

## Build the Windows installer

```bash
pip install pyinstaller
winget install JRSoftware.InnoSetup
tools\build-windows.cmd
```

This builds `dist\UniRGB.exe` (one file, no Python needed) and `dist\UniRGB-Setup-<version>.exe`. The build downloads
PawnIO's official installer and module and refuses to continue unless their SHA-256 hashes match the pinned values in
`tools/fetch_pawnio.py`.

## More

- [CONTRIBUTING.md](CONTRIBUTING.md): adding a device, the safety rules, pull requests
- [SECURITY.md](SECURITY.md): reporting a vulnerability
- [docs/architecture.md](docs/architecture.md) · [docs/architecture-decisions.md](docs/architecture-decisions.md)
- [docs/security-and-safety.md](docs/security-and-safety.md): what UniRGB does and never does with your hardware
- [docs/open-source.md](docs/open-source.md) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): licences and sources
- [docs/roadmap.md](docs/roadmap.md)
