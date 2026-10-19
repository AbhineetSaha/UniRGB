# Security and safety

## v0.2 boundary change (at the user's request)

Direct HID writes are now made to two devices whose protocols are documented by open-source drivers:
the Razer Basilisk V3 Pro (openrazer) and the MSI Mystic Light 761 controller (OpenRGB, board MS-7E70 listed as tested).
Guards: Razer writes are NOSTORE only. MSI writes need MSI Center's lighting stopped, a board string containing `MS-7E70`,
and a saved baseline, and they send only OpenRGB's tested setup layout. SMBus, I²C, EC and firmware remain off-limits.
The table below describes v0.1 and still applies to every other device. Details: [direct-control.md](direct-control.md).

### Elevated CPU-temperature helper (v0.3)

The only code that runs with administrator rights is `unirgb/cpu_temp_helper.py`. It starts only after a UAC prompt and calls
only AMD's signed CLI with read-only arguments (`-a GetPMTableData`, `--api GetCurrentTemperature`); the CLI's
overclocking "Set" calls are never used. It writes one JSON file and exits when the UniRGB process ends.
Caveat: the helper runs from the project folder, which your user account can modify, so anything that can write
there could run elevated at the next prompt. Keep the project in a folder only you control.

### RAM: written only through OpenRGB (user decision, 2026-10-19)

You first asked for risk-free RAM handling, then chose to change RAM colors through OpenRGB, accepting that an SMBus
write can damage a module. How that is contained:
- UniRGB itself still has **no SMBus code** (`tests/test_safety.py` enforces this). It only sends colors to OpenRGB's
  SDK server over TCP. OpenRGB, whose G.Skill/ENE DRAM support is maintained and tested, performs the SMBus access through PawnIO.
- UniRGB's OpenRGB link exposes **only RAM** (OpenRGB device type 1), so OpenRGB never becomes a second writer
  for the board, mouse or keyboard.
- MSI Center's lighting must stay off, or it and OpenRGB would both write the DIMMs.

## Operating boundary (enforced in code)

| UniRGB does | UniRGB never does |
|---|---|
| Opens HID devices with **desired access 0** (query-only) to read descriptors and strings | Read or write HID input, output or feature reports itself |
| Calls Razer's documented Chroma REST API on `localhost:54235` | Touch SMBus, I²C, EC, PCI config space, Super I/O or firmware |
| Talks to OpenRGB's SDK server **only if the user is already running it** | Start, stop or reconfigure vendor services, drivers or apps |
| Queries service state with `SERVICE_QUERY_STATUS` only | Install drivers (e.g. PawnIO), change permissions, need admin |
| Reads MSI's own log file and CIM inventory | Modify vendor configuration or profiles |
| Writes only its own files under `%APPDATA%\UniRGB` and `%LOCALAPPDATA%\UniRGB` | Store credentials. None are used |

Runs as a normal user. No elevation is requested or needed.

## Local attack surface

| Surface | Risk | Mitigation |
|---|---|---|
| HTTP API on 127.0.0.1:47821 | Another local process or a web page drives your lighting | Loopback bind. Host allow-list blocks DNS rebinding. Per-run random token required on POST/DELETE (web pages cannot read it cross-origin). Body cap 256 KB. CSP + `nosniff`. No CORS headers |
| Scene import | Malformed JSON | Strict schema: version check, name regex, color and brightness validation. A file that fails to parse is never overwritten (saves go to `scenes.recovered.json`) |
| Razer Chroma server (not ours) | It sends `Access-Control-Allow-Origin: *`, so any website can change Chroma lighting | Outside UniRGB's control. Documented here. Lighting changes are its only effect |
| `EneIo64.sys` (shipped with MSI Center) | Drivers of this family have historically exposed raw port/memory I/O to user mode | UniRGB never loads or calls it. Worth knowing as part of the system's existing attack surface |
| Logs | Information disclosure | Logs hold device IDs and session URIs only. No secrets exist to leak |

## Hardware-safety risks

| Risk | Mitigation |
|---|---|
| Two programs writing the same controller (flicker, corrupted state) | UniRGB uses only vendor-sanctioned paths. The ownership resolver refuses writes to hardware owned by a higher-priority path. OpenRGB devices carry an explicit conflict warning |
| Leaving devices in UniRGB's colors after exit or crash | Quit → session DELETE. Crash → journal cleanup on next start. Synapse also expires abandoned sessions (observed ≤120 s) |
| Runaway writes (slider drags) | Client throttling plus server-side coalescing. A circuit breaker pauses an adapter after 3 consecutive failures |
| A misbehaving adapter taking down the app | Each adapter runs on its own worker. Exceptions become error results, and timeouts return control to the UI |

## Rollback

UniRGB changes nothing outside its own files. To remove it completely:

```cmd
rmdir /s /q "%APPDATA%\UniRGB" "%LOCALAPPDATA%\UniRGB"
```

Then delete the project folder. Razer lighting returns to the Synapse profile as soon as UniRGB quits (or within
about 2 minutes if it was killed). Nothing in MSI Center, Synapse, Kreo KB Hub or OpenRGB was modified, so nothing
needs restoring there.

## Actions that need your approval (not done)

0. Stopping MSI Center's lighting (`tools\msi-lighting-stop.cmd`, run as admin) to enable MSI direct writes.
1. Downloading/installing MSI's official Mystic Light SDK (would allow board/DIMM control through MSI's own service).
2. Installing OpenRGB + PawnIO driver (kernel driver) for SMBus/I²C devices: higher risk, not recommended while MSI Center runs.
3. Passive USB capture (USBPcap) of Kreo KB Hub traffic to learn the keyboard protocol.
4. Installing Node.js to run `rea` for static analysis of vendor apps.
