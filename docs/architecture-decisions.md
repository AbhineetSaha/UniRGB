# Architecture decisions

## ADR-1 · Language: Python 3 standard library only
* **Options:** Python stdlib · Node/Electron · C#/.NET (WinUI/WPF) · Rust/Tauri.
* **Evidence:** Python 3.14 is the only toolchain on the machine. Node, .NET SDK and Rust are absent, and installing
  them is a system change that needs approval. Every needed OS facility (SetupAPI/hid.dll via `ctypes`, SCM,
  HTTP client and server, JSON) is in the standard library.
* **Decision:** Python, zero third-party dependencies. **Trade-offs:** there is no native UI toolkit beyond Tk, and packaging
  needs Python to be present. Revisit if distribution to other machines becomes a goal (PyInstaller, or a .NET port of the
  adapters).

## ADR-2 · UI: local web page in an Edge `--app` window
* **Options:** Tkinter · local HTML served to an Edge/Chrome app window · pywebview (dependency).
* **Decision:** HTML/CSS/JS served on loopback, opened with `msedge --app`. That gives a modern, responsive UI with
  no dependencies, and Edge ships with Windows 11. Tkinter could not deliver the required polish cheaply.
* **Trade-offs:** a loopback HTTP surface needs hardening (ADR-7). Closing the window does not stop the backend (ADR-8).

## ADR-3 · Razer via the documented Chroma REST API, not direct HID
* **Options:** Chroma REST · Chroma native DLL (`RzChromaSDK64.dll` via ctypes) · direct HID feature reports (OpenRGB-style).
* **Evidence:** REST is live, documented by Razer, and keeps Synapse as the device owner. Direct HID would compete with
  Synapse for the device.
* **Decision:** REST. It needs no DLL loading, the session is visible and easy to debug, and restore is free (DELETE → Synapse
  profile). **Trade-off:** there is no read-back, so confirmation is "api-accepted" and brightness is software-scaled.

## ADR-4 · MSI, Kreo, GPU, DRAM are monitor-only
* **Options:** direct 761-byte MSI HID protocol · MSI private TCP API · MSI official SDK · OpenRGB · monitor-only.
* **Decision:** monitor-only now. MSI Center's service actively writes the same controller, the protocol knowledge
  is third-party, and SMBus/I²C writes are outside the safety rules. Write paths are offered through ChromaLink
  (experimental) or OpenRGB (opt-in, user-run), both labelled as such.

## ADR-5 · Capability levels instead of booleans
* `Support` = supported / experimental / untested / blocked / unsupported on every operation. The UI renders controls only
  for supported, experimental and untested levels, and labels the last two. **Why:** the brief forbids implying support. A boolean
  cannot express "the API accepts it but nobody has seen the LEDs".

## ADR-6 · One single-thread executor per adapter + latest-wins coalescing
* **Options:** global lock · thread per request · asyncio · per-adapter executor.
* **Decision:** a per-adapter executor. Writes to one control path are serialised (no concurrent access to a device),
  separate adapters run in parallel, and a hung adapter blocks only itself. Coalescing keeps slider drags from
  queueing hundreds of writes. A test sends 50 queued writes and fewer than 6 reach the adapter. asyncio was rejected because
  ctypes/urllib calls block anyway.

## ADR-7 · Loopback hardening
* Bind `127.0.0.1`, an allow-list for the Host header (DNS rebinding), a per-run random token embedded in the page and required on
  every mutating request (CSRF), a 256 KB body cap and a CSP. **Why:** observation showed the Chroma server allows
  any origin, and UniRGB must not add a second open door.

## ADR-8 · Lifecycle: lazy session, single instance, journaled crash recovery
* No Chroma session until the first write (discovery never takes lighting away from Synapse).
* Fixed port with `SO_REUSEADDR` off on Windows, so a second launch cannot bind and opens the first instead.
* **Evidence-driven change:** a crash experiment showed the SDK kept an abandoned session alive beyond 25 s
  (documented: 15 s). Added `%LOCALAPPDATA%\UniRGB\chroma_session.json`. A stale session is deleted on the next start
  and on heartbeat or effect failure (`_abandon`). Explicit **Quit** releases everything.

## ADR-9 · Cross-adapter ownership via `physical_key`
* The same hardware can appear through several adapters (inventory HID entry, Chroma, OpenRGB). The registry
  groups by `physical_key` (`usb:VID:PID`, …). A writable entry beats a read-only one, then lower `priority` wins (Razer 10 <
  OpenRGB 30 < MSI 50 < inventory 200). Others are marked `shadowed_by` and refuse writes. **Why:** this blocks the classic
  conflict of OpenRGB writing raw HID to a mouse Synapse owns.

## ADR-10 · `rea` not integrated
* See `repository-analysis.md`. It is an analysis toolkit with no device I/O and needs Node.js.

## ADR-11 · Direct HID adapters (v0.2, user request: bypass vendor apps)
* **Options:** keep vendor APIs only · use OpenRGB as a dependency · implement the documented protocols directly.
* **Decision:** direct implementations in `unirgb/protocols/` + `adapters/razer_direct.py`, `adapters/msi_direct.py`,
  with a shared feature-report transport (`hostos/hid_io.py`). They take priority 5, so they own the hardware when
  reachable. The vendor entries stay as automatic fallback (e.g. mouse asleep → Chroma).
* **Read before write:** both adapters proved the transport with read commands (Razer firmware, MSI GET 0x50) before any write.
* **Evidence-driven details:** `ZERO_LED` brightness reads fail on fw 2.50, so LOGO is used for read-back. NOSTORE vs VARSTORE read-back
  proved the saved profile is untouched. MSI writes are gated on MSI Center's processes because MSI Center streams colors live.
* **Not copied:** openrazer/OpenRGB are GPL. Only protocol facts are used.

## Iteration log

| # | Change | Why / evidence | Tests |
|---|---|---|---|
| 1 | Chroma base URL `127.0.0.1` → `localhost` | Real server: `400 Invalid Hostname` for 127.0.0.1 (HTTP.sys URL reservation) | Hardware discovery now finds the Razer adapter |
| 2 | Investigated a suspected 411 heartbeat bug and **reverted** the change | curl PUT without Content-Length → 411, but `http.client` adds `Content-Length: 0`. Verified the original encoding against the real server (heartbeat `200 {"tick":1}`) | The fake now enforces 411 on PUT/POST without a length, matching the real server |
| 3 | Chroma session journal + stale-session cleanup + `_abandon()` on failures | Crash experiment: session alive at 25 s, gone by 120 s | `test_stale_session_from_crash_is_deleted_on_next_start`, journal assertions in the restore test |
| 4 | Heartbeat restart race fix | Code review: restore then immediate apply could leave no heartbeat thread | Covered by restore/apply tests |
| 5 | Quit button + `/api/quit` | Closing an `--app` window does not stop the backend, so lighting stayed held | E2E: journal cleared, server stopped |
| 6 | `zones: []` and boolean brightness rejected | Unit test caught `[]` slipping through as "no zones" | `test_state_roundtrip_and_validation` |
| 8 | Direct Razer and MSI adapters | User request. Read probes succeeded before writes | `tests/test_direct.py` (11 tests) + real-device run |
| 9 | Brightness read-back via LOGO_LED | `ZERO_LED` read → "failure" on fw 2.50 | Fake device mirrors this behaviour |
| 7 | UI: state card hidden for read-only devices; sim read-back labelled "Simulated" | UI review: avoid implying hardware confirmation | Manual UI check |
