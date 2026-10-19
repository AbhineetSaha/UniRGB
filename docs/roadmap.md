# Roadmap

## Implemented (v0.1.0)

- [x] Query-only HID enumeration, CIM inventory, service-state checks
- [x] Unified registry with desired vs confirmed state and confirmation levels
- [x] Adapter contract, per-adapter isolation, coalescing, timeouts, circuit breaker, ownership resolution
- [x] **Razer Chroma adapter**: Basilisk V3 Pro static color, software brightness, off, experimental zones; ChromaLink (experimental); restore; crash journal
- [x] MSI Mystic Light read-only monitor (zones from MSI's log, service state)
- [x] Inventory for the keyboard, mic, unknown HID device, GPUs and DRAM, with reasons for being read-only
- [x] OpenRGB SDK adapter (opt-in; untested against a real server)
- [x] Multi-device "Sync all", scenes (save, apply, delete, import, export)
- [x] Desktop UI (Edge app window), diagnostics view, Quit/release, single instance
- [x] 46 automated tests plus opt-in real-hardware tests

## Implemented (v0.2)

- [x] Direct HID transport, Razer protocol, MSI 761 protocol
- [x] Razer Basilisk V3 Pro direct: color, native brightness with read-back, zones, partial restore
- [x] MSI Mystic Light direct: setup read, baseline, gated writes, restore (verified on the real board 2026-10-19)

## Next priorities (in order)

1. **User confirmation of physical results.** Do the Basilisk's colors and zones match? Does ChromaLink move the MSI board LEDs?
   Fix the zone map or promote ChromaLink from experimental depending on the answer.
2. **MSI official Mystic Light SDK adapter** (needs approval to install the SDK). Board headers and DIMMs through MSI's own
   service, with read-back (`MLAPI_GetLedColor`), so no contention.
3. **Animated effects engine.** App-driven frames (breathing, spectrum, wave) streamed through `CHROMA_CUSTOM2`. The
   coalescing orchestrator is already the right primitive. Needs a frame-rate cap and a CPU budget test.
4. **Kreo Hive keyboard.** Passive USB capture (approval), protocol notes, then a read-only "identify" probe before any write.
5. **Device-change notifications** (`RegisterDeviceNotification` / CM_Register_Notification) instead of 15 s polling.
6. **Tray icon / autostart** (optional), and packaging (PyInstaller one-file build).
7. Verify the OpenRGB adapter against a real OpenRGB 1.0 server, with MSI lighting turned off.

## Known limitations

- Chroma has no read-back, so Razer state is "api-accepted", never "hardware-readback".
- Another Chroma app with higher priority in Synapse can override UniRGB even when the API reports success.
- Brightness on Razer and OpenRGB paths is color scaling, not hardware brightness.
- Closing the window does not quit. Use **Quit** to hand lighting back.
- Only one Razer device class (mouse) is mapped from HID. Razer keyboards/headsets would need endpoint mapping (`/keyboard`, `/headset`) and their grids.
- Fan control, performance profiles and displays: not implemented. No safe, documented path was found on this machine.
- Windows only for discovery (the HID/SCM modules return nothing on other OSes).

## Open decisions for the user

See "Actions that need your approval" in `security-and-safety.md`.
