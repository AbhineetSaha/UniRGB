"""Read-only probe for ENE DRAM RGB controllers. Run as administrator:

    python -m unirgb_smbus.probe [--module PATH_TO_SmbusPIIX4.bin]

Sends only SMBus read transactions to 0x70-0x77 and prints what answered. Writes nothing.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from .bus import AMD_VENDOR, ENE_DRAM_ADDRESSES, PIIX4_MODULE, PawnIO, ReadOnlySmbus, SmbusMutex

# ENE controllers return their own register offset for 0xA0-0xAF (the identification OpenRGB uses).
SIGNATURE_BASE = 0xA0


def probe(bus: ReadOnlySmbus) -> list[dict]:
    found = []
    for addr in ENE_DRAM_ADDRESSES:
        if bus.read_byte(addr) is None:
            continue
        sig = [bus.read_byte_data(addr, SIGNATURE_BASE + i) for i in range(16)]
        found.append({"address": addr, "signature": sig, "ene": sig == list(range(16))})
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--module", type=Path, default=PIIX4_MODULE, help="PawnIO SmbusPIIX4.bin")
    args = ap.parse_args(argv)
    if sys.platform != "win32" or not ctypes.windll.shell32.IsUserAnAdmin():
        print("Run this from an administrator terminal on Windows (PawnIO needs it).")
        return 2
    if not args.module.is_file():
        print(f"PawnIO module not found: {args.module}.")
        print(r"Run 'python tools\fetch_pawnio.py SmbusPIIX4.bin' first, or pass --module.")
        return 2

    pawn = PawnIO()
    try:
        pawn.load(args.module.read_bytes())
        bus = ReadOnlySmbus(pawn, SmbusMutex())
        ident = bus.identity()
        print(f"SMBus controller: PCI {ident['pci_vendor']:04X}:{ident['pci_device']:04X} "
              f"subsystem {ident['subsys_vendor']:04X}:{ident['subsys_device']:04X}, "
              f"I/O base 0x{ident['smbus_base']:04X}, port {bus.current_port()}")
        if ident["pci_vendor"] != AMD_VENDOR:
            print("Not an AMD SMBus controller; stopping without probing.")
            return 1
        found = probe(bus)
    finally:
        pawn.close()

    if not found:
        print("Nothing answered at 0x70-0x77. Controllers may sit on another port, or OpenRGB has "
              "not remapped them since boot (all DIMMs then share 0x77).")
    for f in found:
        sig = " ".join("--" if b is None else f"{b:02X}" for b in f["signature"])
        print(f"0x{f['address']:02X}: {'ENE controller' if f['ene'] else 'not ENE'}  [{sig}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
