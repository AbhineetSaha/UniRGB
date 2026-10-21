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
  enforces the SMBus rule. The one exception is `unirgb_smbus/`, the RAM lighting work in progress. It can only reach
  ENE DRAM controllers at 0x70–0x77, never SPD hubs (0x50–0x57) or power controllers (0x48–0x4F). Its only write is
  the ENE register pointer, limited to the controller's name and configuration registers (`unirgb_smbus/ene.py`,
  enforced by `tests/test_smbus.py`). Any lighting write needs its own reviewed pull request.
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

**Device Lab** (developer tool, never shipped): `python -m devlab` opens virtual twins of supported devices driven by
UniRGB's real code, with a byte trace, safety tripwires and fault injection. Rehearse any new write path there before
it touches real hardware. See [docs/testing.md](docs/testing.md#device-lab).

## Pull requests

Fork the repository, work on a branch, and open a pull request against `main`. `main` is protected: every change goes
through a pull request, CI (tests, Ruff and the website build) and CodeQL must pass, and the maintainer reviews and
merges. Security problems go to [SECURITY.md](SECURITY.md), not to public issues.
