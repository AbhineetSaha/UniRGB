"""Temperature and fan sources. UniRGB itself never needs administrator rights.

Source order for the CPU temperature (all optional, none bundled):
 1. LibreHardwareMonitor (open source, MPL-2.0) with its "Remote Web Server" enabled:
    UniRGB reads http://127.0.0.1:8085/data.json. LHM does the privileged sensor access and
    also reports fan speeds (read-only monitoring).
 2. AMD Ryzen Master SDK CLI, only if the user installed it AND explicitly starts the elevated
    helper from the UI. The SDK is proprietary (its licence forbids redistribution), so UniRGB never
    ships it and never uses it unless asked. Only read-only calls are made.
 3. nvidia-smi GPU temperature (ships with the NVIDIA driver), shown labelled as GPU.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

AMD_CLI = Path(r"C:\Program Files\AMD\RyzenMasterSDK\AMDRyzenMasterCLI\bin-prebuilt\AMDRyzenMasterCLI.exe")
_CELSIUS = re.compile(r"GetCurrentTemperature[ .]*\s+(-?\d+(?:\.\d+)?)\s*Celsius")
STALE_S = 15.0
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


LHM_URL = "http://127.0.0.1:8085/data.json"
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
CPU_TEMP_NAMES = ("Core (Tctl/Tdie)", "CPU Package", "Package", "Core Max", "Tctl", "Tdie", "CCD1 (Tdie)")


def _num(text):
    m = _NUM.search(str(text or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _walk(node):
    yield node
    for c in node.get("Children") or []:
        yield from _walk(c)


def parse_lhm(doc: dict) -> dict:
    """CPU temperature and fan speeds from LibreHardwareMonitor's data.json tree."""
    cpu, fans = None, []
    nodes = list(_walk(doc))
    temps = [n for n in nodes if str(n.get("SensorId", "")).startswith(("/amdcpu/", "/intelcpu/"))
             and n.get("Type") == "Temperature"]
    for name in CPU_TEMP_NAMES:
        hit = next((n for n in temps if n.get("Text") == name and _num(n.get("Value")) is not None), None)
        if hit:
            cpu = (name, _num(hit.get("Value")))
            break
    if cpu is None:
        vals = [(n.get("Text"), _num(n.get("Value"))) for n in temps if _num(n.get("Value")) is not None]
        if vals:
            cpu = max(vals, key=lambda v: v[1])
    for n in nodes:
        if n.get("Type") == "Fan" and _num(n.get("Value")) is not None:
            fans.append({"name": n.get("Text"), "rpm": round(_num(n.get("Value"))), "id": n.get("SensorId")})
    return {"cpu": cpu, "fans": fans}


def read_lhm(url: str = LHM_URL, timeout: float = 1.0):
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return parse_lhm(json.loads(r.read()))
    except (OSError, ValueError):
        return None


def read_lhm_cpu(url: str = LHM_URL):
    d = read_lhm(url)
    if not d or not d["cpu"]:
        return None
    return Reading(d["cpu"][1], "cpu-lhm", "CPU (LibreHardwareMonitor: %s)" % d["cpu"][0], time.time())


def helper_file() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniRGB" / "cpu_temp.json"


@dataclass
class Reading:
    celsius: float
    source: str        # "cpu-pawnio" | "cpu-lhm" | "cpu-amd" | "gpu-nvidia"
    label: str
    at: float


def parse_amd_cli(text: str) -> float | None:
    m = _CELSIUS.search(text)
    return float(m.group(1)) if m else None


def decode_cli(raw: bytes) -> str:
    """The SDK sample is a UNICODE build: redirected output may be UTF-16 rather than ANSI."""
    if raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16-le", "replace")
    return raw.decode("mbcs" if os.name == "nt" else "utf-8", "replace")


last_cli_output: str = ""


_AMD_COMMANDS = [["-a", "GetPMTableData"], ["--api", "GetCurrentTemperature"]]


def read_amd_cli(timeout: float = 8.0) -> float | None:
    """Only works in an elevated process. Read-only API call."""
    global last_cli_output
    if not AMD_CLI.exists():
        last_cli_output = "AMD CLI not found"
        return None
    # Zen 5 answers "Deprecated API. Use GetPMTableData" to GetCurrentTemperature (observed on the
    # 9800X3D); the PM-table dump prints the same "GetCurrentTemperature ... X Celsius" line.
    for args in list(_AMD_COMMANDS):
        try:
            out = subprocess.run([str(AMD_CLI), *args], capture_output=True, stdin=subprocess.DEVNULL,
                                 timeout=timeout, creationflags=_NOWIN, cwd=str(AMD_CLI.parent))
        except subprocess.TimeoutExpired as e:
            last_cli_output = f"{args[1]} timed out; partial output: {decode_cli(e.stdout or b'')[:300]!r}"
            continue
        except (OSError, subprocess.SubprocessError) as e:
            last_cli_output = f"failed to run: {e}"
            return None
        last_cli_output = f"{args[1]} exit {out.returncode}: " + decode_cli(out.stdout + out.stderr)
        t = parse_amd_cli(last_cli_output)
        if t is not None:
            _AMD_COMMANDS[:] = [args]   # remember the call this CPU answers; skip the dead one next time
            return t
    return None


def read_helper_file(path: Path | None = None, now: float | None = None) -> Reading | None:
    p = path or helper_file()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    now = time.time() if now is None else now
    if not isinstance(d.get("celsius"), (int, float)) or now - float(d.get("at", 0)) > STALE_S:
        return None
    return Reading(float(d["celsius"]), "cpu-amd", "CPU (AMD Ryzen Master)", float(d["at"]))


def read_hw_helper(start=None, request=None) -> Reading | None:
    """CPU temperature from UniRGB's own elevated helper (PawnIO). start() launches it if it is not running."""
    if request is None:
        from .hostos.pipe import request
    r = request({"op": "cpu_temp"})
    if r is None:
        if start:
            start()
        return None
    if not r.get("ok") or not isinstance(r.get("celsius"), (int, float)):
        return None
    return Reading(float(r["celsius"]), "cpu-pawnio", f"{r.get('label', 'CPU')} (UniRGB helper)", time.time())


def read_nvidia(timeout: float = 5.0) -> Reading | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN)
        return Reading(float(out.stdout.strip().splitlines()[0]), "gpu-nvidia", "GPU (nvidia-smi)", time.time())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
