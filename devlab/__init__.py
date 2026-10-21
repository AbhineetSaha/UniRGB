"""UniRGB Device Lab: virtual twins of supported devices for testing UniRGB's code without the hardware.

Developer tool only. It is not part of the app or the installer: the build excludes it, and
tests/test_devlab.py fails if anything in the app imports it.

A pass here proves UniRGB sends the documented bytes and handles faults; it does not prove a real device behaves
the same. Run: python -m devlab
"""
