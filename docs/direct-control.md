# Direct device control

UniRGB talks to supported devices itself, over HID reports, without their vendor apps. When a direct adapter can reach a
device it owns it (priority 5), and any vendor-API entry for the same device is shown as a duplicate. Start with
`--no-direct` to use vendor APIs only.

## Protocol sources

| Device | Protocol | Source of facts |
|---|---|---|
| Razer Basilisk V3 Pro (1532:00AA wired, 1532:00AB HyperSpeed) | 90-byte feature report, transaction ID 0x1F, XOR CRC over bytes 2–87, extended-matrix class 0x0F | openrazer `driver/razercommon.[ch]`, `razerchromacommon.c`, `razermouse_driver.c`; matrix 1×13 from the daemon's `mouse.py` |
| MSI Mystic Light 761 (0DB0:0076) | Setup report 0x50 (290 bytes), per-zone direct report 0x51 | OpenRGB `MSIMotherboard761Controller.cpp` and its board table |
| Kreo Hive RGB / Evision V2 (320F:5055) | Vendor collection FF1C:0092, live "dynamic colors" | OpenRGB's Evision V2 keyboard controller |
| Ant Esports pump display (5131:2007) | 65-byte HID output report `[0x00, 0x40, temp, …]`, bit 7 of `temp` = °F | [AntEsports-Cooler-Controller](https://github.com/neonvarun/AntEsports-Cooler-Controller) (MIT) |

Protocol facts are re-implemented; no code from these projects is copied.

## Razer Basilisk V3 Pro

* **Transport:** feature report 0 on interface 0, through a handle opened without read/write access. Windows holds the
  mouse collection exclusively, but feature reports still pass.
* **Volatile only:** lighting uses NOSTORE, so the profile saved on the mouse is never changed. A sleep/wake, a replug
  or Synapse brings the saved look back, and UniRGB re-applies its color when the mouse wakes.
* **Read-back:** each apply reads the brightness back and fails if it differs. On firmware 2.50 a brightness read with
  `ZERO_LED` returns "failure", so UniRGB reads the LOGO LED instead.
* **Asleep:** when the wireless mouse sleeps, the receiver answers with status 0x04 "timeout". UniRGB shows the mouse
  as **Asleep** and reconnects on the next rescan after it wakes (within about 15 s).
* **Razer Synapse:** Synapse uses the same interface. UniRGB matches replies by command class and ID and retries, so an
  occasional collision costs a retry. When Synapse runs a lighting effect it streams frames (class 0x0F, ID 0x03) many
  times a second, and UniRGB's commands can't get through. UniRGB detects any of Synapse's replies during discovery,
  marks the mouse as controlled by Synapse, and offers **Quit Razer Synapse**.
* **Zones:** columns follow OpenRGB's table (scroll 0, logo 1, strip 2–12). Not yet checked against the physical LEDs.
* **Mouse settings:** DPI and stages, polling rate and sleep timer are read from the mouse. The first values read are
  saved as a baseline so they can be restored.

## MSI Mystic Light 761

* **Board gate:** writes only when the board string contains a board from OpenRGB's tested list (currently `MS-7E70`).
  This controller family has had bricking reports on untested boards.
* **Vendor gate:** writes are refused while `Mystic_Light_Service`, `LightKeeperService` or `LEDKeeper2` run, because
  MSI Center streams colors to the same controller.
* **Baseline:** the first setup read (290 bytes) is saved to `%LOCALAPPDATA%\UniRGB\msi761_baseline.bin` and never
  overwritten. **Return to vendor app** writes it back.
* **What direct mode changes:** JARGB_V2_1–3 and EZ Conn (JAF) are driven per zone with MSI's configured LED count. The
  12 V JRGB1 header is switched off while in direct mode, because this protocol has no direct packet for it. RAM
  lighting is not affected: MSI drives the DIMMs over SMBus, not through this controller.

### Turning on MSI direct control

1. Right-click `tools\msi-lighting-stop.cmd` → **Run as administrator**. It stops MSI's lighting services and
   LEDKeeper2. It disables or uninstalls nothing.
2. Press **Rescan** in UniRGB. "MSI Mystic Light (direct)" becomes controllable.
3. To hand back: **Return to vendor app** in UniRGB, then run `tools\msi-lighting-start.cmd` as administrator, or reboot.

`tools\vendor-autostart-disable.cmd` (as administrator) stops Razer Synapse and MSI Center from starting with Windows,
with a backup; `tools\vendor-autostart-restore.cmd` undoes it. Nothing is uninstalled.

## Kreo Hive RGB

* Only live "dynamic colors" are used; nothing is written to the keyboard's stored profiles.
* A keepalive re-sends the colors every 150 ms. When UniRGB stops or crashes, the keyboard returns to its stored effect
  within about 200 ms by itself.

## Pump temperature display

* **Confirmation first:** 5131:2007 is a generic chip that other gadgets (for example USB relay boards) also use. UniRGB
  sends nothing until the user confirms the device is their cooler display.
* **Temperature sources, in order:** UniRGB's hardware helper (AMD Zen, through PawnIO, if CPU temperature is turned on
  in Settings) → LibreHardwareMonitor's web server → AMD Ryzen Master (only if the user opts in) → GPU temperature from
  `nvidia-smi`, labelled as GPU.
* **No flashing:** the stock panel flashes at 85 °C and above. The default holds the display at 84; "Compress" maps
  75–100 to 75–84; "Raw" sends the real value.
* Pump and fan ARGB lighting come from the motherboard's ARGB headers, not from this device.
