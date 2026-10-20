# Contributing to UniRGB

Thanks for helping. UniRGB talks to real hardware, so the rules below protect other people's devices.

## Adding a device or board

1. **Read before you write.** Open an issue with the device's VID:PID, HID collections (UniRGB → Diagnostics)
   and the output of a *read-only* probe. Never send write commands you have not seen documented.
2. **Name your source.** Every protocol fact needs a public source (spec, open-source driver, or your own
   passive USB capture). Don't copy code from GPL projects into non-GPL contexts. Write your own implementation.
3. **Prefer volatile writes.** Use live/direct modes that revert on their own over writes to a device's flash.
4. **Keep it exact.** Match exact VID/PID (and board IDs for motherboards). Never write to "similar" devices.
5. **Honest support levels.** New capabilities start as `untested`. They become `experimental` after a real-hardware
   test, and `supported` only with a read-back or a confirmed visual check. Record the evidence in
   `docs/device-capability-matrix.md`.

## Hard limits (pull requests that cross these are declined)

- No SMBus, I²C, embedded-controller, Super I/O or firmware-flashing code in UniRGB. `tests/test_safety.py`
  enforces the SMBus part. Use OpenRGB / LibreHardwareMonitor as separate programs instead.
- No bundling of proprietary software or SDKs.
- UniRGB itself must not require administrator rights.

## Development

```bash
python -m unittest discover -s tests -t .
```

Standard library only. Add tests with fake devices (`tests/fakes.py`, `tests/test_direct.py`) for every new protocol.

## Pull requests

Fork the repository, work on a branch, and open a pull request against `main`. `main` is protected: every change
goes through a pull request, CI (the test suite and the website build) must pass, and the maintainer reviews and
merges. Security problems go to [SECURITY.md](SECURITY.md), not to public issues.
