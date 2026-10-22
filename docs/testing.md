# Testing

Run everything from the repository root:

```bash
python -m unittest discover -s tests -t .
ruff check .
```

CI runs the tests on Windows and Ruff on Linux for every pull request. Tests that need Windows APIs (named pipes, the
tray icon, HID) skip themselves on other systems.

## Suites

| File | Covers | Hardware? |
|---|---|---|
| `tests/test_core.py` | Color and state validation, orchestrator (coalescing, timeouts, circuit breaker, failure isolation, concurrent writers), disconnect and reconnect, ownership and shadowing, scenes (round-trip, backup, corrupt-file protection, import/export) | Simulated |
| `tests/test_direct.py` | Razer protocol bytes and CRC, NOSTORE, read-back mismatch, asleep mouse, Synapse streaming, MSI gating, baseline save and restore | Fake devices |
| `tests/test_kreo.py` | Evision V2 framing and checksum, profile writes impossible, bad echoes rejected, static color, ending direct mode | Fake device |
| `tests/test_cooler.py` | Pump-display packets, °F flag, anti-blink modes, temperature-source order, nothing sent before confirmation, blank on quit, settings validation, recovery from write errors | Fakes |
| `tests/test_adapters.py` | Razer Chroma (sessions, encoding, heartbeat, journal and stale-session cleanup), OpenRGB (controller parsing, updates, read-back), MSI log parsing, inventory classification | Fake servers |
| `tests/test_gui.py` | The native window against simulated devices: device list, live color, Sync all, restore, Settings, Scenes, Diagnostics, every device page | Simulated (needs a display) |
| `tests/test_app.py` | Last colors re-applied after a restart or reconnect, restart flags, single instance | Simulated |
| `tests/test_prefs.py` | Preference validation and atomic saves | – |
| `tests/test_system_setup.py` | Task XML, PawnIO install/skip/start decisions, a half-removed PawnIO, removal of only the setup's own files, stale-helper detection | Fakes |
| `tests/test_hardware_helper.py` | Temperature decoding, request handling, a real named-pipe round trip including `stop`, fast give-up without a helper | Real pipe (Windows) |
| `tests/test_tray.py` | The tray icon appears, answers a click and is removed | Real Win32 (Windows) |
| `tests/test_fetch_pawnio.py` | Hash pinning and staging of the bundled PawnIO files | – |
| `tests/test_safety.py` | No SMBus write primitives anywhere in `unirgb/`; RAM inventory stays read-only | – |
| `tests/test_hardware.py` | Real HID enumeration and a full real discovery with no adapter crash. Opt-in Chroma write cycle | **Real** |

Fakes model the documented wire formats and the behaviour seen on real devices, including their errors. Passing
against them proves UniRGB's encoding is self-consistent, not that every device accepts it. When a fake disagrees with
a real device, the fake is corrected.

## Real-hardware tests

Real lighting writes are opt-in. This one changes a Razer mouse's color through Chroma for about 3 s, then hands it back:

```bash
UNIRGB_HW_WRITE=1 python -m unittest tests.test_hardware -v
```

(In cmd, run `set UNIRGB_HW_WRITE=1` first.)

## Device Lab

A developer tool for rehearsing hardware code without the hardware. It is **not part of the app or the installer**:
`tools/build-windows.cmd` excludes it, and `tests/test_devlab.py` fails if the app ever imports it.

```bash
python -m devlab
```

It opens `http://127.0.0.1:47850/` with virtual devices that answer UniRGB's real code byte for byte:

- **Virtual LEDs** show what each device would display.
- **Byte trace:** every transfer, decoded.
- **Tripwires:** anything a real device must never receive stops the test in red. For RAM that means a transfer to an
  SPD hub or power controller, the ENE save command, or a write to an undocumented register.
- **Fault injection:** a busy bus, a device that stops answering.

Currently virtual: ENE DRAM controllers (RAM). A pass proves UniRGB sends the documented bytes and handles faults. It
does not prove a real device behaves the same, so a real-hardware test is still required before raising a support level.

## Reporting a hardware test

A pull request that adds or changes a device, or raises a support level, should include:

1. The device's VID:PID, firmware version (if readable) and, for motherboards, the board ID.
2. What was sent and what came back: acks, read-back values, errors (UniRGB → Diagnostics helps).
3. What you saw on the device itself, including anything that didn't match.
4. How the device was handed back (restore, replug, vendor app) and whether it returned to its previous state.

The device's row in [device-capability-matrix.md](device-capability-matrix.md) is updated from that evidence.

## Manual checks before a release

- Fresh install on a PC without PawnIO: first-start dialog, **Set up now**, one UAC prompt, automatic restart, and the
  pump display reading the CPU temperature from the helper.
- Quit from the tray: no `UniRGB.exe` process left in Task Manager.
- Sign out and in with autostart on: the tray icon appears and saved lighting is re-applied.
- **Remove it** in Settings, and separately an uninstall: the scheduled task and the Program Files folder are gone,
  even while the helper was running.
