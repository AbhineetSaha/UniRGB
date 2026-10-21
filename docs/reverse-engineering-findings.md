# Vendor software notes

How the vendor apps that UniRGB coexists with are put together, as far as can be seen without disassembling them.
Everything here comes from non-invasive sources: installed files, vendor logs, service and socket listings, HID
descriptors read through query-only handles, and documented APIs. No vendor binaries were disassembled.

Confidence: **High** = observed directly or reproduced. **Medium** = strong indirect evidence. **Low** = inference.
Versions noted are the ones examined; newer releases may differ.

## Razer Synapse 4 and the Chroma SDK

```
Synapse UI (RazerAppEngine, Electron)
     │  internal IPC
     ▼
RzSDKServer / RzSDKService ── HTTP.sys listener http://localhost:54235/razer/chromasdk
     │                         per-session listener http://localhost:<random>/chromasdk
     ▼
RzDeviceManager ──► HID (receiver or wired mouse) ──► LEDs
     └─ RzChromaConnectServer (TCP 13331) ──► Chroma Connect partners
```

| Finding | Confidence |
|---|---|
| The Chroma REST listener is HTTP.sys with a URL reservation for host `localhost`. Requests sent to `127.0.0.1` get `400 Invalid Hostname` | High |
| It sends `Access-Control-Allow-Origin: *`, so any web page in a local browser can drive Chroma lighting | High |
| Session flow: POST → `{sessionid, uri}` → PUT effects → DELETE ends the session and Synapse resumes its profile | High |
| A PUT without `Content-Length` is rejected with 411 (`http.client` adds `Content-Length: 0` automatically) | High |
| An abandoned session can outlive the documented 15 s timeout: one still answered 25 s after its client was killed, and was gone by 120 s. UniRGB journals its session and deletes a stale one on the next start | High |
| The REST API cannot read back the current lighting, so Razer devices on this path show "api-accepted" | High |
| Synapse also exposes the mouse as a Windows Dynamic Lighting LampArray (`razerwdl.exe`, HID usage page 0x59) | Medium |
| When Synapse runs a lighting effect, it streams custom-frame commands (class 0x0F, ID 0x03) to the mouse many times a second, which blocks other programs' commands on the same interface | High |
| Synapse re-adds its startup entry (`RazerAppEngine` in the user's Run key) after updates | Medium |

Synapse decides priority between Chroma apps, so a `result: 0` does not guarantee that the LEDs show UniRGB's color.

## MSI Center / Mystic Light

```
MSI Center UI ──► MSI.CentralServer (local TCP) ──► Mystic_Light_Service, LEDKeeper2, LightKeeperService
                                                     │
                                                     ▼
                       HID 0DB0:0076 feature reports (761 bytes) ──► JRGB / JARGB / EZ Conn headers
                       SMBus through MSI's ENE driver            ──► DDR5 DIMM lighting
```

| Finding | Confidence |
|---|---|
| The board controller is HID 0DB0:0076, vendor page FF00, with a 761-byte feature report | High |
| MSI lists its zones (JRGB1, JARGB_V2_1–3, EZ Conn, DDR5 DIMM) in `Log\MysticLight_Test\MysticLight.txt` at start-up | High |
| DIMM lighting goes over SMBus through MSI's ENE driver (`EneIo64.sys`, `SB_SMBUS_SDK.dll`) | Medium |
| The UI-to-backend protocol (local TCP) is undocumented | High |
| MSI's service writes the controller continuously while lighting is enabled, so a second writer causes flicker | High |
| Mystic Light ships a "Razer Sync" module (`MsiRzFX.dll`) for Chroma Connect | High (present) / Low (in use) |

UniRGB's MSI monitor (`msi_mystic.py`) reads the zone list from that log and the service state. Writes go through the
direct adapter only, on tested boards, with MSI's lighting stopped ([direct-control.md](direct-control.md)).

## Kreo KB Hub (Evision keyboards)

| Finding | Confidence |
|---|---|
| The lighting channel is the vendor collection FF1C:0092 (64-byte in/out) on interface 1 | High |
| The vendor app `OemDrv.exe` has no resident service; it talks HID directly while open | High |
| The keyboard's live "dynamic colors" mode reverts to the stored effect when the host stops sending | High |

## GPU and RAM lighting

* **Graphics cards:** lighting usually sits behind an I²C controller on the card. Raw I²C writes are outside UniRGB's
  safety boundary for now.
* **DDR5 RAM:** RGB controllers (ENE) share the SMBus with each module's SPD hub (0x50–0x57) and power controller
  (0x48–0x4F). Writing the wrong address can damage a module, which is why RAM support starts read-only and excludes
  those addresses permanently.
