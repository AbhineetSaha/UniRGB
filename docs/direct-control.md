# Direct device control (vendor apps bypassed)

Since v0.2 UniRGB talks to the hardware itself over HID feature reports. The vendor APIs (Chroma SDK) remain as a
fallback. When a direct adapter can reach a device, it owns it (priority 5 vs 10), and the vendor entry is shown as a duplicate.
Start with `--no-direct` to go back to vendor-only control.

## Protocol sources

| Device | Protocol | Source of facts | Licence note |
|---|---|---|---|
| Razer Basilisk V3 Pro (1532:00AB / 00AA) | Razer 90-byte report, transaction 0x1F, XOR CRC over bytes 2–87, extended-matrix class 0x0F | openrazer `driver/razercommon.[ch]`, `razerchromacommon.c`, `razermouse_driver.c`, daemon `mouse.py` (matrix 1×13) | Protocol facts re-implemented. No openrazer (GPL-2.0) code copied |
| MSI Mystic Light 761 (0DB0:0076) | Setup report 0x50 (290 B), per-zone direct report 0x51 | OpenRGB `MSIMotherboard761Controller.cpp` @ e6a96c6 (2026-10-18). MS-7E70 is in its board table as zone-based direct | Same: facts only. No OpenRGB (GPL-2.0-or-later) code copied |

## Verified on this machine (2026-10-19)

### Razer Basilisk V3 Pro: working directly

| Test | Result |
|---|---|
| Transport | Feature report 0 on interface 0 through a query-only handle (Windows holds the mouse collection exclusively, but feature reports still pass) |
| Asleep mouse | Receiver echoes the command with status 0x04 "timeout". UniRGB marks the device *unavailable* and falls back to Chroma |
| Firmware read | v2.50 |
| Static red / blue 40 % / zones / off | Device status 0x02 "ok" every time, 64–194 ms per apply |
| Brightness read-back | `get brightness` with `ZERO_LED` → "failure" on fw 2.50. With LOGO (0x04) or SCROLL (0x01) it works. Live (NOSTORE) read 102 after setting 102. **Saved (VARSTORE) stayed 84**, which proves UniRGB does not modify the stored profile |
| Apply verification | Each apply reads brightness back and fails if it differs (70 % → 70 %, 25 % → 25 % confirmed) |
| Restore | Live brightness reset to the saved 33 % (84/255) and read back |

Not verified: physical colors and zone positions (the agent cannot see LEDs). Zone columns follow OpenRGB:
scroll 0, logo 1, strip 2–12.

### MSI Mystic Light: working directly (after MSI Center lighting was stopped)

| Test | Result |
|---|---|
| Open | Read/write handle granted while MSI Center runs |
| GET 0x50 | Valid 290-byte setup: JARGB1–3 and JAF in mode 2, LED count 30. JRGB1 active. Rows match OpenRGB's layout |
| Baseline | Saved automatically to `%LOCALAPPDATA%\UniRGB\msi761_baseline.bin` (290 bytes). The first capture is never overwritten |
| Gating | Writes are refused while `Mystic_Light_Service`, `LightKeeperService` or `LEDKeeper2` run. After the user approved the elevated stop script (UAC), all three stayed stopped for more than 15 s and MSI Center did not restart them |
| Direct setup | After the first write, GET 0x50 reads back JARGB1–3 and JAF as mode 9, flags 0x15, 30 LEDs, with other rows off. **Hardware read-back confirms the controller entered direct mode** |
| Color writes | All red · per-zone (green/blue/white/magenta) · cyan 30 % · off: every SET 0x51 accepted, about 28 ms per full apply (5 reports). **The user confirmed visually that the board lights followed the sequence** (red → mixed → dim cyan → off). Which header got which color in the mixed step was not checked individually |
| Restore | Baseline written back. GET 0x50 then matched the saved baseline **byte for byte** |

### Ant Esports ICE-Storm 360 ARGB: pump-cap temperature display (replaces the Ant Esports app)

| Item | Finding |
|---|---|
| Device | The "unidentified" HID 5131:2007 (consumer page, 65-byte reports, no strings) is the pump-cap display. 5131:2007 is a generic chip that other vendors reuse with different framing. It is treated as this cooler because you identified it |
| Protocol | 65-byte HID **output** report: `[0x00, 0x40, temp, …]`, bit 7 of `temp` = °F. Taken from the MIT-licensed [neonvarun/AntEsports-Cooler-Controller](https://github.com/neonvarun/AntEsports-Cooler-Controller) (ICE-Infinity/ICE-Flow family) |
| Display test | Writes of 42, 55, 77 accepted (65/65 bytes) |
| CPU temperature | Ryzen temperature needs a kernel driver and admin rights. AMD's own signed Ryzen Master SDK CLI is used, and its driver (`AMDRyzenMasterDriverV29`) was already installed and running. On this Zen 5 CPU `--api GetCurrentTemperature` answers **"Deprecated API. Use GetPMTableData"**. `-a GetPMTableData` (read-only) works: 47.3–47.6 °C at idle, and you confirmed the pump display showed about 47 |
| Privilege split | The UniRGB server stays unprivileged. `python -m unirgb.cpu_temp_helper` starts elevated (one UAC prompt from the display card), writes `%LOCALAPPDATA%\UniRGB\cpu_temp.json` every few seconds, and exits when UniRGB exits. If the CLI fails 5 times it stops and saves the CLI output in `cpu_temp.error` |
| Fallback | Without the helper the display shows the **GPU** temperature (nvidia-smi, no admin), labelled as GPU in the UI |
| Anti-blink | The stock panel flashes at 85 °C and above. The default holds the display at 84. "Compress" maps 75–100 to 75–84. "Raw" disables both |
| Not here | Pump and fan ARGB run from the motherboard ARGB headers: set them with the MSI Mystic Light (direct) entry |

## Turning on MSI direct control

1. Right-click `tools\msi-lighting-stop.cmd` → **Run as administrator**. It stops the two services and LEDKeeper2. It disables or uninstalls nothing.
2. In UniRGB press **Rescan**. "MSI Mystic Light (direct)" becomes controllable (experimental).
3. To hand back: **Return to vendor app** in UniRGB (writes the saved baseline back), then run `tools\msi-lighting-start.cmd` as administrator, or just reboot.

What direct mode changes on the board, the same as OpenRGB's tested layout:
- JARGB_V2_1, JARGB_V2_2, JARGB_V2_3 and EZ Conn (JAF) are driven per zone, each with MSI's configured LED count (30).
- **The 12 V JRGB1 header is switched off** while in direct mode. This protocol has no direct packet for it.
- **RAM lighting is untouched.** MSI drives the DIMMs over SMBus, not through this USB controller, so they keep whatever
  effect was last stored in them. (An earlier version of this doc said they were switched off. That was an assumption, not an observation.)

## Not done, and why

| Device | Status | Reason |
|---|---|---|
| Kreo Hive RGB (320F:5055) | read-only | Its vendor collection FF1C:0092 is the usage page OpenRGB's Evision drivers use, but 320F:5055 is in neither the V1 nor the V2 detector list. Evision commands write keyboard flash. Sending a guessed protocol version is the "blind replay" the project rules forbid. Next step: passive USB capture (your approval) or a vendor spec |
| G.Skill DDR5 | **through OpenRGB (your decision)**: UniRGB sends colors to OpenRGB, which does the SMBus writes. Earlier rule, now superseded: | You asked for risk-free RAM handling. Any SMBus write carries some risk of corrupting a DIMM's SPD chip, so UniRGB has no RAM write path at all (a test enforces this). Risk-free options: leave the effect stored in the DIMMs, or set it once with MSI Center (the vendor-tested path); the DIMMs keep it after MSI Center is disabled again |
| Gigabyte RTX 5070 Ti | read-only | See the GPU section once it is assessed |

## Risks you are accepting with direct control

- Synapse keeps running unless you quit it and may re-apply its lighting over UniRGB's. Both send feature reports
  to the same interface. UniRGB matches replies by command ID and retries, so a collision costs one retry, not a corrupted state.
- The MSI controller family had bricking reports on **untested** boards in the past. UniRGB refuses to write unless the board
  string contains `MS-7E70` (OpenRGB-tested) and only sends OpenRGB's tested setup layout.
- Nothing here writes persistent storage on the mouse (NOSTORE). The MSI setup is volatile until MSI Center rewrites it.
  A baseline copy is kept regardless.
