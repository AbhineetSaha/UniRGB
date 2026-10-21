# Roadmap

## Done

- Query-only HID enumeration and a read-only inventory that explains why each device isn't controllable
- Unified device model: desired vs confirmed state, confirmation levels, capability levels, ownership between adapters
- Direct control: Razer Basilisk V3 Pro (color, zones, native brightness with read-back, DPI, polling rate, sleep timer,
  battery), MSI Mystic Light 761 on tested boards, Kreo Hive RGB / Evision V2 keyboards
- AIO pump temperature display with CPU temperature from UniRGB's own hardware helper (PawnIO)
- First-start preferences and a one-time admin setup; no prompts on later starts
- Tray icon, background start at sign-in, single instance, clean quit that hands devices back
- Vendor fallbacks: Razer Chroma SDK, OpenRGB (RAM)
- Scenes (save, apply, import, export) and "Sync all"
- Windows installer with a hash-pinned PawnIO bundle; CI, CodeQL and protected `main`

## Next

1. **RAM lighting without OpenRGB.** A read-only SMBus probe for ENE DRAM controllers first, then writes through the
   hardware helper, with SPD hubs and power controllers permanently excluded.
2. **Windows Dynamic Lighting (LampArray).** A standard adapter that controls any device exposing the HID LampArray
   usage, from any vendor.
3. **Uninstall cleanup.** The uninstaller should also remove the hardware helper and its scheduled task. Until then,
   turn off CPU temperature in Settings (which removes them) before uninstalling.
4. **Animated effects engine.** App-driven frames (breathing, spectrum, wave) with a frame-rate cap and a CPU budget test.
5. **Device-change notifications** instead of polling every 15 s.
6. **More devices** through device-support requests: each needs a read-only probe log and a real-hardware test.
7. **Code signing and winget** so Windows stops warning on download.

## Known limitations

- Windows only. Linux and macOS have no device backends.
- Razer zone positions follow OpenRGB's table and haven't been checked against the physical LEDs.
- The Chroma SDK path cannot read lighting back; brightness on Chroma and OpenRGB paths is color scaling.
- An app update needs one admin prompt to refresh the hardware helper.
- CPU temperature through the helper supports AMD Zen CPUs only.
- Fan control is not implemented: no safe, documented path exists yet.
