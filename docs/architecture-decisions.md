# Architecture decisions

Short records of the decisions that shape UniRGB: the options, what was chosen, and the trade-off accepted.

## ADR-1 · Python 3, standard library only
* **Options:** Python stdlib · Node/Electron · C#/.NET · Rust/Tauri.
* **Decision:** Python with zero third-party runtime dependencies. Every needed OS facility (SetupAPI and hid.dll via
  `ctypes`, service queries, named pipes, HTTP client and server, JSON) is in the standard library, so there is nothing
  to audit or update beyond Python itself. PyInstaller packs it into one `.exe` for users.
* **Trade-off:** no native UI toolkit beyond Tk (see ADR-2), and Windows APIs are bound by hand through `ctypes`.

## ADR-2 · UI: a local web page in an Edge `--app` window
* **Options:** Tkinter · local HTML in an Edge/Chrome app window · pywebview (a dependency).
* **Decision:** HTML/CSS/JS served on loopback and opened with `msedge --app`. A modern UI with no dependencies; Edge
  ships with Windows, and any browser works as a fallback.
* **Trade-off:** a loopback HTTP surface that needs hardening (ADR-6).

## ADR-3 · Direct HID first, vendor APIs as fallback
* **Options:** vendor APIs only (Chroma SDK, MSI SDK) · OpenRGB as a backend · own implementations of documented protocols.
* **Decision:** own implementations in `unirgb/protocols/` with direct adapters at priority 5. Vendor paths (Razer
  Chroma at 10, OpenRGB at 30, MSI monitor at 50) stay as fallbacks and are shown as duplicates when the direct path
  owns the device. Using OpenRGB as the backend would make UniRGB a front-end for another program.
* **Rules:** read commands prove the transport before any write; writes are volatile where the device allows it
  (Razer NOSTORE, Kreo live colors, MSI baseline restore); MSI writes need a tested board ID and MSI Center's lighting
  stopped. Only protocol facts are used from GPL projects, never code.

## ADR-4 · Capability levels instead of booleans
* `Support` = supported / experimental / untested / blocked / unsupported on every operation. The UI renders controls
  only for the first three and labels the last two of those. **Why:** a boolean cannot express "the device accepts it
  but nobody has seen the LEDs", and the project must never imply support it hasn't shown.

## ADR-5 · One single-thread executor per adapter, latest-wins coalescing
* **Options:** global lock · thread per request · asyncio · per-adapter executor.
* **Decision:** per-adapter executor. Writes to one control path are serialised, separate adapters run in parallel, and a
  hung adapter blocks only itself. Coalescing keeps slider drags from queueing hundreds of writes (a test sends 50 queued
  writes and fewer than 6 reach the adapter). asyncio was rejected because the `ctypes` calls block anyway.

## ADR-6 · Loopback hardening
* Bind `127.0.0.1`, allow-list the Host header (DNS rebinding), embed a per-run random token in the page and require it
  on every mutating request (CSRF), cap request bodies at 256 KB, and send a CSP. **Why:** some vendor servers on the
  same machine accept requests from any web page, and UniRGB must not add another open door.

## ADR-7 · Cross-adapter ownership via `physical_key`
* The same hardware can appear through several adapters (inventory, direct HID, Chroma, OpenRGB). The registry groups
  records by `physical_key` (`usb:VID:PID`). A writable entry beats a read-only one, then the lower priority wins. Others
  are marked `shadowed_by` and refuse writes, so two UniRGB paths never write the same device.

## ADR-8 · Lifecycle: single instance, background, tray icon
* A fixed port with address reuse off gives a single instance; a second launch opens the first one's window.
* Closing the window keeps lighting applied; **Quit** (button or tray menu) hands devices back. The tray icon is plain
  Win32 through `ctypes` (`hostos/tray.py`) and re-adds itself when Explorer restarts.

## ADR-9 · Privileged features: one-time setup, scheduled task, narrow helper
* **Problem:** reading the CPU temperature on AMD needs a kernel driver and administrator rights, but the app must not
  run elevated, and users shouldn't get a UAC prompt at every start.
* **Options:** run the whole app as admin · prompt for a helper at every start · a Windows service · a scheduled task
  with highest privileges, started on demand.
* **Decision:** the user opts in at first start. A one-time elevated setup installs the open-source PawnIO driver
  (bundled, hash-pinned), copies the helper to an admin-only folder in Program Files, and registers an on-demand task
  with no triggers. The app starts it with `schtasks /run`, so later starts need no prompt.
* **Helper rules:** fixed arguments; modules loaded only from its own folder; requests limited to `ping`, `cpu_temp`
  and `stop`; a named pipe whose ACL admits only the signed-in user and SYSTEM, rejects remote clients and refuses a
  second server; exits on `stop` or after 60 s idle.
* **Trade-off:** an app update makes the Program Files copy stale, which costs one prompt to refresh. Settings detects
  this by size and timestamp and asks.

## ADR-10 · First-start preferences
* Features that need the driver are opt-in and saved in `prefs.json`. Only known keys and booleans are accepted, and
  features that aren't available yet (RAM) can't be switched on. The app starts the helper only when the preference is
  on and the driver is installed.
