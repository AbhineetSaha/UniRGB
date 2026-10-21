# Security and safety

## What runs with which rights

| Part | Rights | Starts when |
|---|---|---|
| UniRGB app (UI server, adapters, tray) | Your normal user account | You start it, or at sign-in if you chose autostart |
| One-time setup (`UniRGB.exe --system-setup`) | Administrator, after a UAC prompt | You click **Set up now** or **Remove it** in Settings |
| Hardware helper (`%ProgramFiles%\UniRGB Hardware Helper\UniRGB.exe --hardware-helper`) | Administrator, through a scheduled task you approved once | UniRGB needs the CPU temperature or RAM lighting, and that feature is turned on in Settings |

The app never runs elevated. Without the optional feature, nothing elevated is installed.

## The hardware helper

* **Fixed requests:** `ping`, `cpu_temp` (AMD Zen temperature register, read-only), `ram_list`, `ram_set`,
  `ram_release` and `stop`. Anything else is refused. RAM requests name a stick by address and are accepted only
  for ENE controllers verified in the same session (see below).
  One newline-terminated JSON request per connection, at most 4 KB.
* **Pipe access:** `\\.\pipe\UniRGB-hardware-helper` admits only the signed-in user (read/write) and SYSTEM, at a
  security level that blocks low-integrity processes such as sandboxed browsers. It rejects remote clients, and the
  helper refuses to start if another program already owns the pipe name.
* **Admin-only files:** the helper and its PawnIO module are copied into Program Files, where standard users can't
  change them, and the helper loads modules only from its own folder. The scheduled task has no trigger, fixed
  arguments, and runs only when started.
* **Lifetime:** the helper exits when UniRGB quits (it is sent `stop`) or after 60 s without requests.
* **Shared hardware locks:** register reads take the system-wide `Global\Access_PCI` mutex that other hardware tools
  (LibreHardwareMonitor, HWiNFO, OpenRGB) use, so they never access the same registers at the same time.
* **PawnIO:** the driver is installed from its official signed installer, bundled unmodified and checked against a
  pinned SHA-256 at build time.

## RAM lighting

* Only ENE DRAM controllers at 0x70–0x76 that answer the ENE signature and identify as a supported version with its
  LED count are used. 0x77 is never used: controllers all share it until something remaps them, and UniRGB does not
  remap.
* SPD hubs (0x50–0x57) and power controllers (0x48–0x4F) cannot be addressed by the code at all.
* Writes are limited to the direct-color registers, direct mode on/off and "apply". The command that saves to the
  stick's own memory cannot be sent, so nothing UniRGB writes survives a power-off.
* Every transfer holds the system-wide SMBus lock that other hardware tools use.
* New RAM code is rehearsed in the Device Lab (`python -m devlab`) against virtual sticks with tripwires before it
  runs on real hardware.

## What UniRGB does and never does

| Does | Never does |
|---|---|
| Opens HID devices to read descriptors and strings, and sends reports only to supported devices with an exact VID:PID match | Write SMBus, I²C, embedded-controller, Super I/O or firmware |
| Writes volatile lighting where the device allows it (Razer NOSTORE, Kreo live colors) | Change the profiles stored on your devices |
| Talks to OpenRGB's SDK server and the Razer Chroma SDK only if you are already running them | Install anything except PawnIO and the helper, and only with your approval |
| Quits Razer Synapse only when you click **Quit Razer Synapse** | Change vendor apps' settings or uninstall them |
| Writes its own files under `%APPDATA%\UniRGB` and `%LOCALAPPDATA%\UniRGB` | Store credentials (none are used) or send data off your PC |

## Local attack surface

| Surface | Risk | Mitigation |
|---|---|---|
| HTTP API on `127.0.0.1:47821` | Another local process or a web page drives your lighting | Loopback bind. Host allow-list blocks DNS rebinding. A per-run random token is required on every mutating request (web pages can't read it cross-origin). 256 KB body cap. CSP and `nosniff`. No CORS headers |
| Hardware helper pipe | Another program asks the elevated helper to do something | Fixed request list, user-only ACL, no remote clients, read-only requests (see above) |
| Scene import | Malformed JSON | Strict schema: version check, name pattern, color and brightness validation. An unreadable scenes file is never overwritten |
| Razer Chroma server (not UniRGB's) | It accepts requests from any web page | Outside UniRGB's control; lighting changes are its only effect |
| Logs | Information disclosure | Logs hold device IDs and states only. No secrets exist to leak |

## Hardware-safety measures

| Risk | Mitigation |
|---|---|
| Two programs writing the same controller (flicker, corrupted state) | UniRGB's own paths never overlap (ownership by `physical_key`). MSI writes are refused while MSI Center's lighting runs. Synapse streaming to the mouse is detected and reported |
| Writing to the wrong motherboard | MSI writes need a board ID from the tested list |
| Leaving devices in UniRGB's colors | Quit hands devices back. Volatile modes revert on their own after a crash. The MSI baseline is kept on disk |
| Runaway writes (slider drags) | Client throttling and server-side coalescing. A circuit breaker pauses an adapter after 3 consecutive failures |
| A misbehaving adapter taking down the app | Each adapter runs on its own worker. Exceptions become error results, and timeouts return control to the UI |

## Removing UniRGB completely

1. Uninstall UniRGB from Windows Settings → Apps. If the one-time setup ran, the uninstaller asks for administrator
   rights once and removes the scheduled task and the helper folder in Program Files. (**Remove it** in Settings does
   the same without uninstalling.)
2. Optional: uninstall PawnIO from Windows Settings → Apps, if no other program uses it. UniRGB leaves it installed
   because other hardware tools may rely on it.
3. Optional: delete your settings and scenes:

```cmd
rmdir /s /q "%APPDATA%\UniRGB" "%LOCALAPPDATA%\UniRGB"
```

Devices return to their own stored lighting when UniRGB quits; nothing in Synapse, MSI Center, Kreo KB Hub or OpenRGB
is changed.
