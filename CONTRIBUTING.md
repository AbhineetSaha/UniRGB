# Contributing to UniRGB

Thanks for helping. UniRGB talks to real hardware, so the rules below protect other people's devices.

## Adding a device or board

1. **Read before you write.** Open a [device-support issue](https://github.com/AbhineetSaha/UniRGB/issues/new/choose)
   with the device's VID:PID, its HID collections (UniRGB → Diagnostics) and the output of a *read-only* probe.
   Never send write commands you have not seen documented.
2. **Name your source.** Every protocol fact needs a public source: a spec, an open-source driver, or your own
   passive USB capture. Don't copy code from other projects. Write your own implementation and name the source in the
   module's docstring and in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
3. **Prefer volatile writes.** Use live or direct modes that revert on their own over writes to a device's flash.
4. **Keep it exact.** Match the exact VID:PID (and board IDs for motherboards). Never write to "similar" devices.
5. **Honest support levels.** New capabilities start as `untested`. They become `experimental` after a real-hardware
   test, and `supported` only with a read-back or a confirmed visual check. Record the evidence in
   [docs/device-capability-matrix.md](docs/device-capability-matrix.md).
6. **Add a fake.** Every protocol gets tests against a fake device (`tests/fakes.py`, `tests/test_direct.py`) that
   mirrors what the real device answers, including its errors.

## Hard limits (pull requests that cross these are declined)

- **The main app stays unprivileged.** Code that needs administrator rights goes only into the hardware helper
  (`unirgb/hardware_helper.py`), which answers a fixed list of requests and takes no arguments that change what it
  does. New helper requests need a clear reason and a test.
- **No SMBus or I²C writes, no embedded-controller, Super I/O or firmware-flashing code.** `tests/test_safety.py`
  enforces the SMBus rule. RAM support is being designed separately, read-only first, with a fixed list of addresses
  that may never be touched.
- **No proprietary software or SDKs in the installer.** Bundled components must be open source, unmodified and
  hash-pinned (see `tools/fetch_pawnio.py`).
- **No new dependencies.** The app uses the Python standard library only.

## Development

```bash
python -m unittest discover -s tests -t .
ruff check .
```

See [docs/testing.md](docs/testing.md) for the opt-in real-hardware tests and what to report from a hardware test.
Run the app with fake devices using `python -m unirgb --simulate`.

## Pull requests

Fork the repository, work on a branch, and open a pull request against `main`. `main` is protected: every change goes
through a pull request, CI (tests, Ruff and the website build) and CodeQL must pass, and the maintainer reviews and
merges. Security problems go to [SECURITY.md](SECURITY.md), not to public issues.
