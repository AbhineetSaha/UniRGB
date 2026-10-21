"""Probe for ENE DRAM RGB controllers (read-only unless you ask for more). Run as administrator:

    python -m unirgb_smbus.probe [--identify | --color-test ADDRESS] [--module PATH_TO_SmbusPIIX4.bin]

Without --identify: sends only SMBus read transactions to 0x70-0x77 and prints what answered.
With --identify: also reads each confirmed ENE controller's name and configuration table, which needs
register-pointer writes (see ene.py). No lighting is changed by either.
With --color-test 0x71: after you type YES, shows red on that one stick for 10 s, then hands it back to its
stored effect (step 2). Nothing is saved to the stick. Rehearse it first in the Device Lab: python -m devlab
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from .ene import EneLighting, EneReader, color_test
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
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--identify", action="store_true", help="also read controller names and LED configuration")
    mode.add_argument("--color-test", type=lambda v: int(v, 16), metavar="ADDRESS",
                      help="step 2 on one stick, e.g. 0x71: red for 10 s, then hand back")
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
        lock = SmbusMutex()
        bus = ReadOnlySmbus(pawn, lock)
        ident = bus.identity()
        print(f"SMBus controller: PCI {ident['pci_vendor']:04X}:{ident['pci_device']:04X} "
              f"subsystem {ident['subsys_vendor']:04X}:{ident['subsys_device']:04X}, "
              f"I/O base 0x{ident['smbus_base']:04X}, port {bus.current_port()}")
        if ident["pci_vendor"] != AMD_VENDOR:
            print("Not an AMD SMBus controller; stopping without probing.")
            return 1
        found = probe(bus)
        confirmed = {f["address"] for f in found if f["ene"]}
        ids = [EneReader(pawn, lock, confirmed).identify(a) for a in sorted(confirmed)] if args.identify else []
        if args.color_test is not None:
            return _color_test(EneLighting(EneReader(pawn, lock, confirmed)), args.color_test, confirmed)
    finally:
        pawn.close()

    if not found:
        print("Nothing answered at 0x70-0x77. Controllers may sit on another port, or OpenRGB has "
              "not remapped them since boot (all DIMMs then share 0x77).")
    for f in found:
        sig = " ".join("--" if b is None else f"{b:02X}" for b in f["signature"])
        print(f"0x{f['address']:02X}: {'ENE controller' if f['ene'] else 'not ENE'}  [{sig}]")
    for i in ids:
        if i is None:
            print("  a controller stopped answering during identification; stopped reading it")
            continue
        print(f"0x{i['address']:02X}: name {i['name']!r}, LED count candidates {i['led_count_candidates']}")
        if i["config"] is not None:
            for row in range(0, len(i["config"]), 16):
                print("  config +%02X: %s" % (row, " ".join(f"{b:02X}" for b in i["config"][row:row + 16])))
    return 0


def _color_test(lighting: EneLighting, addr: int, confirmed: set[int]) -> int:
    if addr not in confirmed:
        print(f"0x{addr:02X} did not answer as an ENE controller in this run; nothing written.")
        return 1
    info = lighting.verify(addr)
    print(f"0x{addr:02X}: {info and info['name']}, LED count {info and info['led_count_candidates']}")
    if input(f"Type YES to show red on 0x{addr:02X} for 10 seconds, then hand it back: ").strip() != "YES":
        print("Cancelled; nothing written.")
        return 0
    print("Red for 10 seconds (Ctrl+C hands it back early)...")
    try:
        print(color_test(lighting, addr))
    except KeyboardInterrupt:
        print("Interrupted. UniRGB tried to switch direct mode off; check that the stick shows its usual effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
