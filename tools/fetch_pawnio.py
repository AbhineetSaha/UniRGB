"""Download the pinned PawnIO files the installer bundles, check their SHA-256, stage them in build\\pawnio.

Run by tools\\build-windows.cmd before Inno Setup. A hash mismatch stops the build: these files install
a kernel driver on users' machines. Layout matches unirgb.system_setup.bundle_dir().
"""
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "build" / "pawnio"
SETUP = ("https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe",
         "1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032")
MODULES = ("https://github.com/namazso/PawnIO.Modules/releases/download/0.2.11/release_0_2_11.zip",
           "43608cb89bc84247fef1368a139013f7d043e17db6d6c8dfc9b46bf0905a81f4")
LICENSE = ("https://raw.githubusercontent.com/namazso/PawnIO/2.2.0/COPYING",
           "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643")
NEEDED_MODULES = ("AMDFamily17.bin", "SmbusPIIX4.bin")   # CPU temperature; RAM lighting (AMD SMBus)


def fetch(url: str, sha256: str, urlopen=urllib.request.urlopen) -> bytes:
    data = urlopen(url, timeout=60).read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise SystemExit(f"SHA-256 mismatch for {url}: expected {sha256}, got {got}")
    return data


def main(extra: list[str] = ()) -> None:
    """Stage the installer's PawnIO files. Extra module names are for development only (e.g. the RAM probe)."""
    shutil.rmtree(OUT, ignore_errors=True)   # never ship a module left over from an older pin
    (OUT / "modules").mkdir(parents=True)
    (OUT / "PawnIO_setup.exe").write_bytes(fetch(*SETUP))
    z = zipfile.ZipFile(io.BytesIO(fetch(*MODULES)))
    for name in (*NEEDED_MODULES, *extra):   # KeyError if a name isn't in the pinned release
        (OUT / "modules" / name).write_bytes(z.read(name))
    (OUT / "PawnIO.Modules-LGPL-2.1.txt").write_bytes(z.read("COPYING"))
    (OUT / "PawnIO-GPL-2.0.txt").write_bytes(fetch(*LICENSE))
    print(f"Staged PawnIO files in {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
