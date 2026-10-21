# Device capability matrix

Legend: **S** supported (implemented and confirmed on real hardware by a read-back or a visual check) · **E**
experimental (the device accepts it; the physical result is not fully verified) · **U** untested (implemented, never run
against real hardware) · **B** blocked (possible in principle, deliberately not done) · **–** not available on this path.

| Device (adapter) | Discover | Read state | Color | Brightness | Effects | Zones | Restore | After a crash |
|---|---|---|---|---|---|---|---|---|
| **Razer Basilisk V3 Pro, direct HID** (`razer-hid`) | S (firmware read) | S: brightness (hardware read-back) | S (device ack) | S (native, read back) | static, off | E (OpenRGB column map) | E: saved brightness restored; colors return on sleep/wake or replug | nothing persistent was changed (NOSTORE) |
| **MSI Mystic Light 761, direct HID** (`msi-hid`) | S (setup read) | setup only | S, blocked while MSI Center's lighting runs | E (software scaling) | static, off | E (JARGB1–3, EZ Conn) | S (saved baseline written back and read back) | baseline file survives crashes |
| **Kreo Hive RGB / Evision V2, direct HID** (`kreo-hid`) | S (capabilities read) | – | E (device ack) | E (software scaling) | static, off | – | S (ends direct mode) | the keyboard reverts by itself within about 0.2 s |
| **Ant Esports pump display** (`cooler`) | S | – | – | – | temperature display | – | display blanked on quit | the feed restarts with the app |
| Razer devices via Chroma SDK (`razer`) | S | – (the API has no read) | S | E (software scaling) | static, off | E (9×7 grid) | S (session ended, Synapse profile returns) | stale session deleted on next start |
| Chroma Connect / ChromaLink (`razer`) | S | – | E | E | static, off | – | S | S |
| RAM via OpenRGB (`openrgb`) | E | E (OpenRGB read-back) | E | E (software scaling) | static, off | – | E | – |
| MSI controller monitor (`msi`) | S | B | B | B | B | listed | – | – |
| GPU lighting (`inventory`) | S | B | B | B | B | – | – | – |
| **RAM, ENE DRAM controllers via the hardware helper** (`ram`) | S (name and LED count verified) | – | E (device ack) | E (software scaling) | static, off | – | S (direct mode off: stored effect returns) | nothing persistent was changed (never saved) |
| `[SIM]` devices (`--simulate` only) | S* | S* | S* | S* | S* | S* | S* | – |

\* Simulation only. Proves the architecture, not hardware.

## Tested hardware

These results come from the maintainer's PC. Other boards, firmware versions and receivers may behave differently;
reports from other hardware are welcome in a [device-support issue](https://github.com/AbhineetSaha/UniRGB/issues/new/choose).

| Device | Firmware / board | Result |
|---|---|---|
| Razer Basilisk V3 Pro via HyperSpeed receiver (1532:00AB) | firmware 2.50 | Static, brightness, zones and off acknowledged in 64–194 ms. Brightness read back exactly. The saved (VARSTORE) brightness stayed unchanged |
| MSI Mystic Light 761 (0DB0:0076) | MS-7E70 (X870E GAMING PLUS WIFI) | Direct mode confirmed by setup read-back. Colors visually confirmed. Restore matched the baseline byte for byte |
| Kreo Hive RGB (320F:5055) | – | Whole-keyboard color acknowledged; reverts to its stored effect when UniRGB stops |
| Ant Esports ICE-Storm 360 pump display (5131:2007) | – | Temperatures displayed as sent; CPU temperature through the hardware helper on a Ryzen 7 9800X3D (Zen 5) |
| RAM: 2 × G.Skill DDR5, ENE `AUDA0-E6K5-0101` at 0x71 / 0x73 | MS-7E70, AMD FCH SMBus | Identified (8 LEDs each). Direct red on one stick for 10 s, then back to its stored effect, by UniRGB's own code. Also colors through OpenRGB 1.1 |

## Why each B

| Device | Reason |
|---|---|
| MSI controller monitor | Superseded by the direct adapter on tested boards. On other boards the 761-byte protocol is unverified, and MSI's own service writes the same controller |
| GPU | Lighting sits behind I²C on the graphics card, which is outside UniRGB's safety boundary for now |

Protocol details and the evidence behind each **S**: [direct-control.md](direct-control.md).
