# Device capability matrix

Legend: **S** supported (implemented and exercised against this device or API) · **E** experimental (API accepts
it, physical effect not verified) · **U** untested (implemented, never run against real hardware) · **B** blocked
(possible in principle, deliberately not done) · **–** not available on this path.

"Exercised" means the vendor API returned success. The agent cannot see LEDs, so no row claims a visually
verified color. See the open questions in `reverse-engineering-findings.md`.

| Device (adapter) | Discover | Read state | Color | Brightness | Effects | Zones | Speed | Fan | Profiles (scenes) | Restore original | Crash recovery |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Razer Basilisk V3 Pro, direct HID (`razer-hid`)** | S (firmware read) | S: brightness only (hardware read-back) | S (device ack) | S (native, read back) | static, off: S | E (1×13 frame, OpenRGB column map) | – | – | S | E: partial (saved brightness restored; colors return on wake/replug) | n/a (NOSTORE: nothing persistent changed) |
| **MSI Mystic Light 761, direct HID (`msi-hid`)** | S (setup read) | – (setup only) | B while MSI Center runs, else S (accepted, setup read back, user saw the colors) | B / E (software scaling) | static, off | B / E (JARGB1–3, JAF) | – | – | S | E (saved baseline written back) | baseline file survives crashes |
| **Ant Esports ICE-Storm 360 display (`cooler`)** | S | – | – | – | – | – | – | – | settings persisted | blank on disable | display feed restarts with the app |
| Razer Basilisk V3 Pro (`razer`) | S | – (API has no read) | S | S (software scaling) | static, off: S | E (scroll, logo, underglow via 9×7 grid) | – | – | S | S (end session → Synapse profile) | S (journal + stale-session delete on next start; Synapse also expires it in 25–120 s) |
| Chroma Connect / ChromaLink (`razer`) | S | – | E | E | static, off: E | – | – | – | S | S | S |
| MSI Mystic Light controller 0DB0:0076 (`msi`) | S | B | B | B | B | B (zones listed from MSI log) | B | – | – | – | n/a |
| DDR5 DIMMs (`inventory`) | S | B | B | B | B | – | – | – | – | – | n/a |
| Gigabyte RTX 5070 Ti (`inventory`) | S | B | B | B | B | – | – | – | – | – | n/a |
| Kreo Hive RGB 320F:5055 (`inventory`) | S | B | B | B | B | B | B | – | – | – | n/a |
| USB microphone 31B2:0011 (`inventory`) | S | – | – | – | – | – | – | – | – | – | n/a |
| Any OpenRGB controller (`openrgb`) | U | U | U | U (software scaling) | static, off: U | U | – | – | U | – | n/a |
| `[SIM]` devices (`sim`, only with `--simulate`) | S* | S* | S* | S* | S* | S* | – | – | S* | S* | n/a |

\* Simulation only. Proves the architecture, not hardware.

## Evidence for each S

| Claim | Evidence |
|---|---|
| Basilisk discovery | HID strings "Razer Basilisk V3 Pro", usage 01:02, plus Chroma `GET` answered |
| Basilisk color, brightness, off | `{"result":0}` for CHROMA_STATIC (including brightness-scaled colors) and CHROMA_NONE, 2026-10-19. `tests/test_hardware.py::HardwareChromaWrite` passes with `UNIRGB_HW_WRITE=1` |
| Basilisk zones (E) | `CHROMA_CUSTOM2` accepted. The mapping of grid cells to physical LEDs is unverified |
| Restore | DELETE returns `{"result":0}`. The session port then refuses connections |
| Crash recovery | Experiment: killed client, session alive at 25 s, gone at 120 s. Journal cleanup covered by `test_stale_session_from_crash_is_deleted_on_next_start` |
| MSI zones listed | `MysticLight.txt` ResetItem lines |
| Scenes | `tests/test_core.py::SceneTests`, `tests/test_server.py::test_scene_flow` |

Direct-control evidence: see [direct-control.md](direct-control.md).

## Why each B

| Device | Reason |
|---|---|
| MSI controller | No official SDK installed. The direct 761-byte HID protocol is community-reverse-engineered, and MSI's service writes the same controller (contention) |
| DDR5 (`inventory` entry) | UniRGB has no SMBus code. RAM colors go through the `openrgb` adapter (RAM only) by user decision |
| GPU | I²C writes are outside UniRGB's safety boundary (assessment pending) |
| Kreo keyboard | Undocumented vendor protocol. No read-back or ack known |
