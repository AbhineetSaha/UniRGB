# Reverse-engineering findings

Everything here comes from non-invasive sources: installed files and metadata, vendor logs, service and socket
listings, HID descriptors read with query-only handles, documented vendor APIs, and controlled, reversible
calls to the documented Razer Chroma REST API. No firmware was touched. No undocumented HID, SMBus or I²C
writes were made, and no vendor binaries were disassembled.

Confidence: **High** = observed directly or reproduced. **Medium** = strong indirect evidence. **Low** = plausible inference.

## 1. Razer Synapse 4 / Chroma SDK (Basilisk V3 Pro)

```
Synapse UI (RazerAppEngine, Electron)
     │  internal IPC (not inspected)
     ▼
RzSDKServer / RzSDKService ── HTTP.sys listener http://localhost:54235/razer/chromasdk   ◄── UniRGB
     │                         per-session listener http://localhost:<random>/chromasdk
     ▼
RzDeviceManager(Ex) ──► HID (receiver 1532:00AB) ──► mouse LEDs
     └─ RzChromaConnectServer (TCP 13331) ──► Chroma Connect partners (e.g. MSI Center "Razer Sync")
```

| Finding | Confidence | Evidence |
|---|---|---|
| The Chroma REST API is live, version core 4.00.02 / device 4.00.03 | High | `GET` returned `{"core":"4.00.02","device":"4.00.03","version":"4.00.03"}` |
| The listener is HTTP.sys with a URL reservation for host `localhost`. Requests sent to `127.0.0.1` get `400 Invalid Hostname` | High | Reproduced with curl and urllib |
| It sends `Access-Control-Allow-Origin: *`, so any web page in a local browser can drive Chroma lighting | High | Response headers |
| Session flow: POST → `{sessionid, uri}` → PUT effects → DELETE ends the session and Synapse resumes its profile | High | Exercised. After DELETE the session port refuses connections |
| `CHROMA_STATIC`, `CHROMA_CUSTOM2` (9×7 grid), `CHROMA_NONE` on `/mouse` return `{"result":0}`. `CHROMA_STATIC` on `/chromalink` returns 0 | High (API) / **unverified (LEDs)** | Real calls on 2026-10-19 |
| A PUT without a `Content-Length` header is rejected with 411. Python's `http.client` adds `Content-Length: 0` automatically | High | curl vs urllib comparison |
| **An abandoned session is not expired at the documented 15 s.** One was still answering heartbeats 25 s after its client was killed, and it was gone by 120 s | High | Two crash experiments (process killed with `os._exit`) |
| The REST API has no call to read back the current lighting | High | API surface. This is why Razer devices show "api-accepted" confirmation |
| Synapse also exposes the mouse as a Windows Dynamic Lighting LampArray (`razerwdl.exe`, HID usage page 0x59) | Medium | Process path + HID usage 0059:0001 on MI_03/MI_04 |
| Effect latency: first call about 580 ms (includes session creation), then about 1 ms median and 26 ms maximum over 20 writes | High | Measured |

Coexistence: UniRGB is one Chroma "app" among others. Synapse decides priority between Chroma apps, so a
`result: 0` does not guarantee the LEDs show UniRGB's color if another app has priority.

## 2. MSI Center / Mystic Light (board headers, DDR5)

```
MSI Center UI ──► MSI.CentralServer (TCP 127.0.0.1:32683/33683) ──► Mystic_Light_Service, LEDKeeper2, LightKeeperService
                                                                     │
                     MLModule.dll / MysticLight_AllDevice.dll / MsiHid*.dll
                                                                     ▼
                                       HID 0DB0:0076 feature reports (761 B)  ──► JRGB/JARGB/EZ Conn headers
                                       SMBus (SB_SMBUS_SDK.dll, EneIo64.sys)  ──► DDR5 DIMM lighting
```

| Finding | Confidence | Evidence |
|---|---|---|
| The board controller is HID 0DB0:0076, vendor page FF00, 761-byte feature report | High | HidP_GetCaps |
| MSI drives zones JRGB1, JARGB_V2_1, JARGB_V2_2, JARGB_V2_3, EZ Conn and DDR5 DIMM | High | `Log\MysticLight_Test\MysticLight.txt` ResetItem lines from today's start-up |
| Mystic Light runs a "Razer Sync" module at start-up (`-Razer Sync Init`) and ships `MsiRzFX.dll` | High (exists) / Low (active) | Log + file list. Whether sync is turned on in the UI is unknown |
| DIMM lighting goes over SMBus through MSI's ENE driver `EneIo64.sys` / `SB_SMBUS_SDK.dll` | Medium | Files present + "DDR5 DIMM" zone |
| The UI-to-backend protocol on 32683/33683/26822 is undocumented | High (undocumented) | No public docs. Not probed |
| MSI's public Mystic Light SDK (`MysticLight_SDK.dll`) is **not installed** | High | File search |
| OpenRGB 1.0 detected this controller as "MSI MYSTIC LIGHT" on 2026-10-06 | High | `%APPDATA%\OpenRGB\logs\OpenRGB_20261006_213343.log` |

**Why UniRGB does not write here:** the only available write paths are (a) the 761-byte feature-report
protocol known from OpenRGB's reverse engineering, while MSI's service writes the same controller, which
risks races and flicker and fails the "do not blindly replay unknown commands" rule, or (b) MSI's private
local TCP API, which is undocumented. Supported routes, in order of preference: MSI's official SDK (needs
approval to download and install), Chroma Connect if Razer Sync is on (experimental entry in UniRGB), or the
OpenRGB SDK server with MSI lighting turned off.

## 3. Kreo Hive RGB keyboard (Evision 320F:5055)

| Finding | Confidence | Evidence |
|---|---|---|
| Evision-based firmware. The lighting/config channel is most likely vendor collection FF1C:0092 (64-byte in/out) on MI_01, plus a 65-byte feature report on MI_00 | Medium | HID caps. Typical layout for Evision OEM boards |
| Vendor app `OemDrv.exe` ("Kreo KB Hub") has no resident service or SDK. Profiles for Hive 75 / Hive 75 Tri-Mode / Hive 98 live under `Dev\kb` | High | Install folder |
| OpenRGB 1.0 enumerated the device but registered **no** controller for it | High | OpenRGB log |
| Protocol is undocumented | High | No public spec found locally |

**Next safe step (needs approval):** passive capture of HID traffic (USBPcap/Wireshark) while the user changes
a color in Kreo KB Hub, then compare against OpenRGB's Evision controller. Write support comes only after the
command set is understood and a read-back or ack exists.

## 4. GPU, DRAM and other devices

* **Gigabyte RTX 5070 Ti:** lighting sits behind an I²C controller on the GPU bus (OpenRGB registered "Nvidia
  NvAPI I2C on GPU 0" but found no Gigabyte controller). Raw I²C writes are outside the safety boundary. **Blocked.**
* **G.Skill DDR5:** SMBus. OpenRGB could not open the SMBus (PawnIO not installed). MSI already drives it. **Blocked.**
* **31B2:0011 microphone and 5131:2007:** no lighting interface. 5131:2007 is unidentified.

## Open questions

1. Is Mystic Light's Razer Sync turned on? If yes, does the ChromaLink entry move the board LEDs? (User to observe.)
2. Do the Chroma 9×7 zone coordinates (scroll 2,3 / logo 7,3 / underglow edges) match the Basilisk's physical LEDs? (User to observe.)
3. Kreo protocol: needs a passive capture with approval.
4. Would the user accept installing MSI's official Mystic Light SDK or OpenRGB (with PawnIO) to extend coverage?
