# Testing

Run everything from the project root:

```bash
python -m unittest discover -s tests -t .
```

Real lighting writes are opt-in (they change your mouse color for about 3 s, then hand it back to Synapse):

```bash
UNIRGB_HW_WRITE=1 python -m unittest tests.test_hardware -v
```

(In cmd: `set UNIRGB_HW_WRITE=1` first.)

## Suites

| File | Covers | Hardware? |
|---|---|---|
| `tests/test_core.py` | Color/state validation, orchestrator validation, read-only rejection, coalescing, exception and discovery-failure isolation, timeouts, circuit breaker, disconnect/reconnect, ownership/shadowing, 8-thread concurrent writers, restore; scenes round-trip, backup, bad names, corrupt-file protection, import/export, multi-device apply | Simulated |
| `tests/test_adapters.py` | Razer: lazy session, BGR encoding, brightness, CUSTOM2 grid, heartbeat, session loss and recreation, error codes, restore, journal and stale-session recovery, unreachable server. OpenRGB: controller parsing (v3 and v0 servers, matrix zones, unsolicited packets), UPDATELEDS payload, read-back, absent server. MSI log parsing, monitor-only caps. Inventory classification, virtual-GPU skip, DRAM summary | Fakes (`tests/fakes.py`) |
| `tests/test_server.py` | Token embedding, CSRF token and Host checks, apply/restore/error codes, scene endpoints, 404s | Simulated |
| `tests/test_hardware.py` | Real HID enumeration. Full real discovery with no adapter crash. Opt-in Chroma static, zone and off cycle + restore | **Real** |

Fakes model documented wire formats. Passing against them proves UniRGB's encoding is self-consistent. It does
**not** prove a real server accepts it. Where a fake disagreed with reality (the HTTP.sys 411 rule), the fake was
corrected to match observed behaviour.

## Results (2026-10-19, Windows 11 26200, Python 3.14.8)

| Run | Result |
|---|---|
| Full suite | **46 tests, OK, 1 skipped** (the hardware-write test without the env flag), about 10 s |
| `UNIRGB_HW_WRITE=1 tests.test_hardware` | **3 tests, OK**. Chroma accepted static, zone and off commands. Restore ended the session |
| End-to-end, real app (`python -m unirgb --no-window`) | API apply to the Basilisk → `ok, api-accepted`. MSI apply → refused (`monitor-only`). Second instance → exits 0 without binding. Quit → server stopped, Chroma journal removed |
| UI (in-app browser, `--simulate`) | Device list grouping, selection, color swatch → apply → state card shows requested and confirmed, zone toggles, read-only device view with blocked capabilities |

## v0.2 direct control (2026-10-19)

| Run | Result |
|---|---|
| Full suite | **57 tests, OK, 1 skipped** (adds `tests/test_direct.py`: protocol bytes, CRC, NOSTORE, read-back mismatch, asleep → unavailable, MSI gating, baseline save/restore, never overwriting the first baseline) |
| Razer direct, real mouse | firmware v2.50. Static, 40 %, zones, off all acknowledged (64–194 ms). Brightness 70 % and 25 % read back exactly. Restore → saved 33 % read back |
| MSI direct, real controller | With MSI Center lighting stopped (user-approved UAC): setup read back as direct mode. Red, per-zone, 30 % and off accepted (about 28 ms each) and **visually confirmed by the user**. Restore → setup identical to the baseline |

## v0.3 cooler display (2026-10-19)

| Run | Result |
|---|---|
| Full suite | **69 tests, OK, 1 skipped** (adds `tests/test_cooler.py`: packet layout, °F flag, anti-blink, AMD CLI parsing incl. UTF-16, helper-file staleness, GPU fallback, CPU preference, settings validation and persistence, blank on disable, recovery from write errors) |
| Real display | Test values 42/55/77 accepted. Live feed: GPU 41–42 °C before the helper, then CPU 47–48 °C after the helper started. **You confirmed the pump display showed about 47** |
| Real CPU sensor | `GetCurrentTemperature` deprecated on Zen 5 (captured CLI output). `GetPMTableData` → 47.3–47.6 °C |

## Hardware validation status

| Device | What was validated | What was NOT |
|---|---|---|
| Razer Basilisk V3 Pro | Discovery. Chroma accepted static, brightness-scaled, CUSTOM2 zones and off. Session restore. 20 rapid writes: 0.8 / 0.9 / 26 ms (min/median/max). Crash: abandoned session alive at 25 s, gone at 120 s | **Physical LED colors were not observed by the agent.** Zone-to-LED placement unverified |
| ChromaLink | API accepted CHROMA_STATIC | Whether any physical light (e.g. MSI board via Razer Sync) changed |
| MSI controller, Kreo, DRAM, GPU, mic, 5131:2007 | Discovery and metadata only | No writes, by design |
| OpenRGB adapter | Fake server only | No real OpenRGB server was running. Every capability is **untested** |

## Reliability and performance

| Measurement | Result |
|---|---|
| Idle CPU, 60 s, background rescan every 15 s | 0.03 % of one core |
| Memory | 37 MB working set / 23 MB private / 14 threads |
| Full discovery | 1.2–1.5 s with the CIM query. Periodic rescans skip CIM |
| Coalescing | 50 queued writes with a 50 ms adapter delay → fewer than 6 executed, final state correct |
| Concurrency | 8 threads × 25 writes over 2 devices, no errors |

**Not yet done:** multi-hour soak test; physical USB unplug/replug cycles (only simulated disconnects are
tested); long high-frequency streaming against real Chroma.

## v0.4 RAM through OpenRGB 1.1 (2026-10-19)

| Run | Result |
|---|---|
| Full suite | **76 tests, OK, 1 skipped** (adds a regression test: OpenRGB health checks must never bare-connect) |
| OpenRGB setup | Only the "ENE SMBus DRAM" detector enabled; 2 controllers registered (ENE DRAM at SMBus 0x71 and 0x73) |
| Bug found and fixed | UniRGB's old health check opened and closed TCP connections without a handshake, which wedged OpenRGB's server. Now one persistent, handshaken connection is used. After the fix, 35 s of rescans added 0 server errors and no CLOSE_WAIT sockets |
| RAM colors via UniRGB | Red, green, blue 40% and restore of the original `#757aff` were each accepted for both DIMMs (28–41 ms); OpenRGB read back exactly the colors sent. Physical colors not yet confirmed by you |
