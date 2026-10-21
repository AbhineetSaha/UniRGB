# Security policy

UniRGB writes to real hardware, so a bug that sends the wrong bytes to a device counts as a security issue,
along with the usual kind: for example, a way for a web page to reach UniRGB's local server, or a way for another
program to make UniRGB's elevated hardware helper do anything beyond its fixed list of requests.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through GitHub:
[Security → Report a vulnerability](https://github.com/AbhineetSaha/UniRGB/security/advisories/new).

Include the UniRGB version, your Windows version, the device (VID:PID) if hardware is involved, and steps to
reproduce. You'll get a reply as soon as the maintainer can, and credit in the advisory if you want it.

## Supported versions

Only the [latest release](https://github.com/AbhineetSaha/UniRGB/releases/latest) gets fixes.
