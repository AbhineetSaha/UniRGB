# System inventory (reference machine)

The adapters were developed and verified on this PC. Other machines will differ.

Audit date: 2026-10-19. Methods: CIM/WMI queries, `Get-PnpDevice`, registry uninstall keys, service list,
listening sockets, and UniRGB's own query-only HID enumerator (`unirgb/hostos/windows_hid.py`). No device
reports were sent during the audit.

## Platform

| Item | Value | Source |
|---|---|---|
| OS | Windows 11 Pro 10.0.26200, 64-bit | `Win32_OperatingSystem` |
| CPU | AMD Ryzen 7 9800X3D (8C/8T reported) | `Win32_Processor` |
| Motherboard | MSI X870E GAMING PLUS WIFI (MS-7E70), BIOS 1.A50 (2026-01-20) | `Win32_BaseBoard`, `Win32_BIOS` |
| RAM | 2 × 16 GB G.Skill DDR5-6000, part `F5-6000J3636F16G` | `Win32_PhysicalMemory` |
| GPU (discrete) | NVIDIA GeForce RTX 5070 Ti, board vendor Gigabyte (subsystem 1458:41A8), driver 617.42 | `Win32_VideoController` |
| GPU (integrated) | AMD Radeon Graphics (1002:13C0) | `Win32_VideoController` |
| Virtual display | Parsec Virtual Display Adapter (ROOT\DISPLAY) | `Win32_VideoController` |
| Storage | Crucial CT1000E100SSD8 (1 TB NVMe), Toshiba DT01ACA050 (500 GB HDD) | `Win32_DiskDrive` |
| Bluetooth | Qualcomm FastConnect 7800 (USB 0489:E10A) | PnP |
| Toolchains | Python 3.14.8, Git 2.56. No Node.js, .NET SDK, Rust or Go | `Get-Command` |

## USB / HID devices

Status key: **Confirmed** = identity read from the device or its descriptors. **Inferred** = deduced from IDs or
related evidence. **Unidentified** = nothing reliable.

| Device | VID:PID | Status | HID collections (usage page:usage) | Driver / owner | Lighting control path |
|---|---|---|---|---|---|
| MSI Mystic Light controller (onboard) | 0DB0:0076 | Confirmed: strings "MSI / MYSTIC LIGHT", serial prefix `7E70` matches the board | FF00:0001, in/out 64 B, **feature 761 B** | HID class; driven by MSI Center `Mystic_Light_Service` | MSI Center (no public SDK installed). OpenRGB knows the protocol |
| Razer Basilisk V3 Pro (via HyperSpeed receiver) | 1532:00AB | Confirmed: strings "Razer / Razer Basilisk V3 Pro". OpenRGB logged wired PID 00AA on 2026-10-06 | 0001:0002 mouse, 0001:0006 kbd, 000C consumer, 0059:0001 (×2, LampArray), 91-byte feature on MI_00 | Razer Synapse 4 | **Razer Chroma SDK REST: used by UniRGB** |
| Kreo Hive RGB keyboard | 320F:5055 | Confirmed: strings "Evision / Kreo Hive RGB" | 0001:0006, 0001:0080, 000C, **FF1C:0092 (64 B in/out)**, 0001:0002 | HID class; vendor app Kreo KB Hub (`OemDrv.exe`) | Undocumented vendor protocol. OpenRGB 1.0 did not register it |
| USB condenser microphone | 31B2:0011 | Confirmed: "DCMT Technology / USB Condenser Microphone" | 000C:0001 only | USB Audio + HID | No lighting interface |
| Unknown HID device | 5131:2007 | Unidentified: no strings | 000C:0001, 65 B in/out/feature | HID class | None identified |
| Bluetooth adapter | 0489:E10A | Confirmed | n/a | Qualcomm | n/a |

## Internal RGB components

| Component | Status | Evidence | Who drives it |
|---|---|---|---|
| Board RGB headers JRGB1, JARGB_V2_1..3, EZ Conn | Confirmed (listed by MSI) | `MysticLight.txt` "ResetItem" lines | MSI Mystic Light controller (0DB0:0076) |
| DDR5 DIMM lighting | Inferred: the part number is a G.Skill Trident Z5-family kit; MSI lists a "DDR5 DIMM" zone | CIM part number + MSI log | MSI Mystic Light over SMBus |
| GPU lighting | Inferred (Gigabyte RTX 50 boards usually carry RGB) | Subsystem 1458 = Gigabyte | Nothing installed. OpenRGB found the NvAPI I2C bus but no Gigabyte controller |
| Fans / AIO | Not detected as separate devices | No USB fan or AIO controllers enumerated. MSI Center has fan modules installed | Board Super I/O (MSI Center). Out of scope |

## Installed device software

| Software | Version | Install location | Processes / services | Local interfaces |
|---|---|---|---|---|
| Razer Synapse 4 + Chroma | 4.0.827 | `C:\Program Files\Razer`, `...\Razer Chroma SDK` | RazerAppEngine (×9, Electron), RzSDKServer/RzSDKService, RzChromaConnectServer/Manager, RzDeviceManager(Ex), Razer Elevation Service, `razerwdl.exe` (LampArray bridge) | **Chroma REST `localhost:54235`** (HTTP.sys, needs Host `localhost`) reports core 4.00.02 / device 4.00.03. Also TCP 1337 and ::1:13337 (RzSDKServer), 13331 (Chroma Connect) |
| Chroma SDK native DLLs | RzChromaSDK64 3.8.0.238 | `C:\Windows\System32` | n/a | Native C API (not used, REST chosen) |
| MSI Center (+ SDK package) | 3.2026.0911.01 | `C:\Program Files (x86)\MSI\MSI Center` | MSI_Center_Service, MSI_Case_Service, Mystic_Light_Service, MSI.CentralServer, MSI.TerminalServer, LEDKeeper2, LightKeeperService, MSI.True Color, MSI_LAN_Manager_Tool | TCP 127.0.0.1:32683/33683 (CentralServer), 26822 (TerminalServer), 55699 (LAN Manager). All undocumented |
| Kreo KB Hub | Cfg Ver 0x200 | `C:\Program Files (x86)\Kreo KB Hub` | none resident | none (UI talks HID directly) |
| OpenRGB | v1.0 (commit 81bbe18, 2026-09-11), logs only | `%APPDATA%\OpenRGB` (config/logs). Program folder holds only `service_config` | not running | SDK server would be TCP 6742 |
| NVIDIA App / driver | 11.0.9.251 / 617.42 | standard | NvContainer services | none relevant to RGB |
| AMD chipset (I2C, GPIO2, PSP drivers), Ryzen Master SDK | 7.12.04.858 | `C:\AMD` | AMD services | none used |
| Parsec + virtual display/USB drivers | 150-105c | standard | n/a | n/a |

## Not found

No Corsair iCUE, SignalRGB, ASUS Armoury Crate, Gigabyte Control Center/RGB Fusion, NZXT CAM, Lian Li L-Connect,
or Logitech G HUB. MSI Center bundles Corsair/ENE/Nanoleaf/Philips Hue plug-ins, but none of that hardware was detected.
