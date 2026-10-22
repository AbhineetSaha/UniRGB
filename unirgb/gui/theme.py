"""Colors, fonts and ttk styles for UniRGB's native window.

Fluent-style look (Windows 11 Settings): rounded cards, pill chips and soft controls. Rounded shapes are
anti-aliased RGBA images drawn here and fed to ttk image elements, so it needs nothing beyond the standard library.
"""
from __future__ import annotations

import base64
import colorsys
import math
import struct
import sys
import tkinter as tk
import zlib
from tkinter import font as tkfont, ttk


def dark_mode() -> bool:
    """Follow Windows' app mode (Settings > Personalization > Colors). Dark elsewhere."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return True


DARK = dict(BG="#15171e", SIDE="#111319", PANEL="#1b1e27", PANEL2="#242834", HOVER="#2b3040", LINE="#252a36",
            TEXT="#e2e5ee", MUTED="#878da0", ACCENT="#8b80f0", ACCENT_HOVER="#9d94f4", ON_ACCENT="#ffffff",
            OK="#6cc9a1", WARN="#e3b86e", BAD="#e98585", INFO="#82b3ea", SELECT="#24233a")
LIGHT = dict(BG="#f4f5f9", SIDE="#eceef4", PANEL="#ffffff", PANEL2="#f2f3f8", HOVER="#e8eaf1", LINE="#e4e6ee",
             TEXT="#262a35", MUTED="#6c7284", ACCENT="#7468e4", ACCENT_HOVER="#867bea", ON_ACCENT="#ffffff",
             OK="#2f9a6c", WARN="#ad7a22", BAD="#c65454", INFO="#3d7cc4", SELECT="#ebe9fc")

# Module-level names other modules read as T.BG etc. apply() picks the palette; dark until then.
BG = SIDE = PANEL = PANEL2 = HOVER = LINE = TEXT = MUTED = ACCENT = ACCENT_HOVER = ON_ACCENT = ""
OK = WARN = BAD = INFO = SELECT = ""
FONT = SMALL = TITLE = SUBTITLE = CARD_TITLE = MONO = ICON = ("Segoe UI", 10)
RADIUS = 8
CARD_RADIUS = 14

SUPPORT_LABEL = {"supported": "Supported", "experimental": "Experimental", "untested": "Untested",
                 "blocked": "Blocked", "unsupported": "Not available"}
SUPPORT_COLOR: dict[str, str] = {}
CONNECTION: dict[str, tuple[str, str]] = {}

_images: dict[tuple, tk.PhotoImage] = {}
_scale = 1.0


def _set_palette(dark: bool) -> None:
    globals().update(DARK if dark else LIGHT)
    SUPPORT_COLOR.update(supported=OK, experimental=WARN, untested=WARN, blocked=BAD, unsupported=MUTED)
    CONNECTION.update({"connected": ("Connected", OK), "monitor-only": ("Monitor only", INFO),
                       "unavailable": ("Unavailable", MUTED), "asleep": ("Asleep", INFO), "error": ("Error", BAD)})


_set_palette(True)


def mix(a: str, b: str, t: float) -> str:
    """Blend color a toward b by t (0..1)."""
    ca, cb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


# ---------- tiny anti-aliased rasterizer (signed distance fields) -> PNG -> PhotoImage ----------
def _png(w: int, h: int, px: bytearray) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\0" + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _rrect(x0, y0, x1, y1, r):
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - r, (y1 - y0) / 2 - r

    def d(x, y):
        qx, qy = abs(x - cx) - hw, abs(y - cy) - hh
        return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
    return d


def _circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def _segment(ax, ay, bx, by, w):
    def d(x, y):
        px, py, vx, vy = x - ax, y - ay, bx - ax, by - ay
        t = max(0.0, min(1.0, (px * vx + py * vy) / (vx * vx + vy * vy)))
        return math.hypot(px - vx * t, py - vy * t) - w / 2
    return d


def _draw(w: int, h: int, layers) -> bytearray:
    """layers: [(sdf, "#rrggbb")], painted in order with 'over' compositing on a transparent canvas."""
    px = bytearray(w * h * 4)
    cols = [(f, tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))) for f, c in layers]
    for y in range(h):
        for x in range(w):
            rgb, a = (0.0, 0.0, 0.0), 0.0
            for f, col in cols:
                s = max(0.0, min(1.0, 0.5 - f(x + 0.5, y + 0.5)))
                if s:
                    na = s + a * (1 - s)
                    rgb = tuple((c * s + v * a * (1 - s)) / na for v, c in zip(rgb, col))
                    a = na
            px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((*(round(v) for v in rgb), round(a * 255)))
    return px


def image(key: tuple, w: int, h: int, layers) -> tk.PhotoImage:
    if key not in _images:
        data = base64.b64encode(_png(w, h, _draw(w, h, layers))).decode()
        _images[key] = tk.PhotoImage(data=data, format="png")
    return _images[key]


def S(n: float) -> int:
    """Pixels scaled for the display's DPI."""
    return max(1, round(n * _scale))


def box(fill: str, line: str | None = None, r: int = RADIUS, size: int = 0) -> tk.PhotoImage:
    """A rounded rectangle (optionally outlined) for 9-slice stretching, or a fixed-size swatch when size is set."""
    n, rr = (S(size) if size else S(r) * 2 + 8), S(r)   # border = radius + 2 leaves a middle to stretch
    inset = 1 if line else 0
    layers = [(_rrect(0, 0, n, n, rr), line)] if line else []
    layers.append((_rrect(inset, inset, n - inset, n - inset, max(0, rr - inset)), fill))
    small = image(("box", fill, line, r, size), n, n, layers)
    return small if size else _grow(small, rr + 2, ("big", fill, line, r))


def _grow(src: tk.PhotoImage, b: int, key: tuple, mid: int = 192) -> tk.PhotoImage:
    """The same 9-slice image with a large middle. ttk tiles the middle, so a tiny one means thousands of
    alpha-blended draws per card (seconds per page); copied in C by Tk, this costs nothing."""
    if key not in _images:
        n, N = src.width(), 2 * b + mid
        dst = tk.PhotoImage(width=N, height=N)
        spans = ((0, b, 0, b), (b, n - b, b, N - b), (n - b, n, N - b, N))   # (from, from_end, to, to_end) per axis
        for fx0, fx1, tx0, tx1 in spans:
            for fy0, fy1, ty0, ty1 in spans:
                dst.tk.call(dst, "copy", src, "-from", fx0, fy0, fx1, fy1, "-to", tx0, ty0, tx1, ty1,
                            "-compositingrule", "set")
        _images[key] = dst
    return _images[key]


def swatch_image(color: str, size: int, circle=False, hover=False, selected=False, bg: str | None = None):
    """A color tile or circle; selected adds an outer ring with a gap, hover a brighter edge."""
    n = S(size)
    r = n / 2 if circle else max(3, n // 4)

    def shape(i):
        return _rrect(i, i, n - i, n - i, max(0.0, r - i))
    edge = TEXT if hover else mix(color, TEXT, .3)
    layers = [(shape(0), TEXT), (shape(S(2)), bg or PANEL)] if selected else []
    inner = S(4) if selected else 0
    layers += [(shape(inner), edge), (shape(inner + 1), color)]
    return image(("sw", color, size, circle, hover, selected, bg), n, n, layers)


def hue_bar(w: int, h: int) -> tk.PhotoImage:
    """A rounded rainbow strip: x maps to hue at full saturation and value."""
    if ("hue", w, h) not in _images:
        mask, px = _rrect(0, 0, w, h, h / 2), bytearray(w * h * 4)
        cols = [bytes(round(c * 255) for c in colorsys.hsv_to_rgb(x / (w - 1), 1, 1)) for x in range(w)]
        for y in range(h):
            for x in range(w):
                a = max(0.0, min(1.0, 0.5 - mask(x + 0.5, y + 0.5)))
                px[(y * w + x) * 4:(y * w + x) * 4 + 4] = cols[x] + bytes((round(a * 255),))
        _images[("hue", w, h)] = tk.PhotoImage(data=base64.b64encode(_png(w, h, px)).decode(), format="png")
    return _images[("hue", w, h)]


def pill(fill: str, w: int, h: int) -> tk.PhotoImage:
    return image(("pill", fill, w, h), w, h, [(_rrect(0, 0, w, h, w / 2), fill)])


def dot(fill: str, size: int = 10, ring: str | None = None) -> tk.PhotoImage:
    n = S(size)
    layers = [(_circle(n / 2, n / 2, n / 2), ring)] if ring else []
    layers.append((_circle(n / 2, n / 2, n / 2 - (S(2) if ring else 0)), fill))
    return image(("dot", fill, size, ring), n, n, layers)


def device_icon(color: str, status: str) -> tk.PhotoImage:
    """The device's color as a rounded tile, with a status dot in the corner (like a presence badge)."""
    n, b = S(24), S(10)
    c = n - b / 2
    layers = [(_rrect(0, 0, n - S(4), n - S(4), S(6)), mix(LINE, TEXT, .15)),
              (_rrect(1, 1, n - S(4) - 1, n - S(4) - 1, S(6) - 1), color),
              (_circle(c, c, b / 2), SIDE), (_circle(c, c, b / 2 - S(2)), status)]
    return image(("dev", color, status), n, n, layers)


def check_image(on: bool, enabled: bool, radio: bool) -> tk.PhotoImage:
    """A check box or radio dot; the image is wider than the box to leave a gap before the label."""
    n = S(18)
    edge = (MUTED if enabled else LINE) if not on else (ACCENT if enabled else MUTED)
    fill = (ACCENT if enabled else MUTED) if on else PANEL2
    if radio:
        layers = [(_circle(n / 2, n / 2, n / 2 - 0.5), edge), (_circle(n / 2, n / 2, n / 2 - 1.5), fill)]
        if on:
            layers.append((_circle(n / 2, n / 2, S(3.5)), ON_ACCENT))
    else:
        layers = [(_rrect(0.5, 0.5, n - 0.5, n - 0.5, S(4)), edge), (_rrect(1.5, 1.5, n - 1.5, n - 1.5, S(3)), fill)]
        if on:
            a = _segment(n * .27, n * .52, n * .43, n * .68, S(1.8))
            b = _segment(n * .43, n * .68, n * .74, n * .34, S(1.8))
            layers.append((lambda x, y: min(a(x, y), b(x, y)), ON_ACCENT))
    return image(("chk", on, enabled, radio), n + S(8), n, layers)


def chevron(color: str) -> tk.PhotoImage:
    w, h = S(12), S(8)
    a, b = _segment(S(2), S(2), w / 2, h - S(2), S(1.6)), _segment(w / 2, h - S(2), w - S(2), S(2), S(1.6))
    return image(("chev", color), w, h, [(lambda x, y: min(a(x, y), b(x, y)), color)])


def logo(size: int = 32) -> tk.PhotoImage | None:
    """The app icon's PNG entry closest to size, from logo.ico (its frames are stored as PNG)."""
    from pathlib import Path
    try:
        d = (Path(__file__).parent.parent / "ui" / "logo.ico").read_bytes()
    except OSError:
        return None
    entries = [struct.unpack("<BBBBHHII", d[6 + 16 * i:22 + 16 * i]) for i in range(struct.unpack("<H", d[4:6])[0])]
    _w, *_, n, off = min(entries, key=lambda e: abs((e[0] or 256) - S(size)))
    if d[off:off + 4] != b"\x89PNG":
        return None
    if ("logo", size) not in _images:
        _images[("logo", size)] = tk.PhotoImage(data=base64.b64encode(d[off:off + n]).decode(), format="png")
    return _images[("logo", size)]


def chip_style(color: str, bg: str | None = None) -> str:
    """A rounded pill label tinted with color, for status and tags. Created on first use."""
    bg = bg or BG
    name = f"C{color[1:]}{bg[1:]}.Chip.TLabel"
    if ("chip", name) not in _images:
        s = ttk.Style()
        img = box(mix(bg, color, .14), mix(bg, color, .32), 8)
        _images[("chip", name)] = img
        s.element_create(f"{name}.bg", "image", img, border=S(8) + 2, sticky="nsew", padding=0,
                         width=2 * S(8) + 4, height=2 * S(8) + 4)
        s.layout(name, [(f"{name}.bg", {"sticky": "nsew", "children": [
            ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
        s.configure(name, foreground=color, background=bg, font=SMALL, padding=(S(10), S(3)))
    return name


def _family(*names: str) -> str:
    have = set(tkfont.families())
    return next((n for n in names if n in have), names[-1])


def title_bar(win) -> None:
    """Ask Windows 10/11 for a title bar that matches the theme (no effect elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1 if BG == DARK["BG"] else 0)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (19 on older Windows 10 builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except (OSError, AttributeError):
        pass


def apply(root) -> None:
    global FONT, SMALL, TITLE, SUBTITLE, CARD_TITLE, MONO, ICON, _scale
    _images.clear()   # images belong to one Tk interpreter
    _scale = root.winfo_fpixels("1i") / 96
    _set_palette(dark_mode())
    text = _family("Segoe UI Variable Text", "Segoe UI")
    semi = _family("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
    disp = _family("Segoe UI Variable Display Semib", "Segoe UI Semibold")
    FONT, SMALL, MONO = (text, 10), (text, 9), (_family("Cascadia Mono", "Consolas"), 9)
    TITLE, SUBTITLE, CARD_TITLE = (disp, 20), (disp, 14), (semi, 11)
    ICON = (_family("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol"), 11)

    root.configure(bg=BG)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):   # not *Font: that would override ttk style fonts
        tkfont.nametofont(name).configure(family=FONT[0], size=FONT[1])
    for k, v in (("background", PANEL2), ("foreground", TEXT), ("selectBackground", ACCENT),
                 ("selectForeground", ON_ACCENT), ("borderWidth", 0), ("font", FONT)):
        root.option_add(f"*TCombobox*Listbox.{k}", v)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL2, bordercolor=LINE, lightcolor=LINE,
                darkcolor=LINE, troughcolor=PANEL2, focuscolor=PANEL2, selectbackground=ACCENT,
                selectforeground=ON_ACCENT, insertcolor=TEXT, font=FONT)

    # frames and labels: plain on the window, Panel inside cards, Side in the device list
    for name, bg in (("", BG), ("Panel.", PANEL), ("Side.", SIDE)):
        s.configure(f"{name}TFrame", background=bg)
        s.configure(f"{name}TLabel", background=bg, foreground=TEXT)
    s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=SMALL)
    s.configure("MutedBg.TLabel", background=BG, foreground=MUTED, font=SMALL)
    s.configure("MutedSide.TLabel", background=SIDE, foreground=MUTED, font=SMALL)
    s.configure("Title.TLabel", background=BG, font=TITLE)
    s.configure("Brand.TLabel", background=BG, font=SUBTITLE)
    s.configure("CardTitle.TLabel", background=PANEL, foreground=TEXT, font=CARD_TITLE)
    s.configure("Field.TLabel", background=PANEL, foreground=MUTED)

    # rounded cards and banners: a 9-slice image element under the usual frame padding
    r, cr = S(RADIUS) + 2, S(CARD_RADIUS) + 2
    banner, info = mix(PANEL, WARN, .08), mix(PANEL, INFO, .07)
    for name, img in (("Card", box(PANEL, LINE, CARD_RADIUS)), ("Banner", box(banner, mix(PANEL, WARN, .24), 10)),
                      ("Info", box(info, mix(PANEL, INFO, .18), 10))):
        b = cr if name == "Card" else S(10) + 2
        s.element_create(f"{name}.bg", "image", img, border=b, sticky="nsew", padding=0, width=2 * b, height=2 * b)
        s.layout(f"{name}.TFrame", [(f"{name}.bg", {"sticky": "nsew"})])
        s.configure(f"{name}.TFrame", background=BG)
        s.configure(f"Panel.{name}.TFrame", background=PANEL)
    s.configure("Banner.TLabel", background=banner, foreground=TEXT)
    s.configure("Info.TLabel", background=info, foreground=TEXT)

    # buttons: default (filled), Primary (accent), Danger (red text), Ghost (flat until hovered)
    def button(style, fill, hover, press, fg, line=None, bg=PANEL):
        el = f"{style}.bg"   # style is a full name such as "Primary.TButton"
        s.element_create(el, "image", box(fill, line), ("disabled", box(PANEL2 if fill != bg else bg)),
                         ("pressed", box(press, line)), ("active", box(hover, line)), border=r, sticky="nsew", padding=0,
                         width=2 * r, height=2 * r)
        s.layout(style, [(el, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        s.configure(style, foreground=fg, padding=(S(14), S(5)), anchor="center", background=bg)
        s.map(style, foreground=[("disabled", MUTED)])
    press = mix(HOVER, TEXT, .08)
    button("TButton", PANEL2, HOVER, press, TEXT, LINE)
    button("Primary.TButton", ACCENT, ACCENT_HOVER, mix(ACCENT, "#000000", .15), ON_ACCENT)
    button("Danger.TButton", PANEL2, mix(PANEL2, BAD, .18), mix(PANEL2, BAD, .28), BAD, LINE)
    button("Ghost.TButton", BG, HOVER, press, TEXT, bg=BG)
    button("Link.TButton", PANEL, HOVER, press, ACCENT)
    s.configure("Ghost.TButton", padding=(S(10), S(5)))
    s.configure("Bad.Ghost.TButton", foreground=BAD)
    for base in ("TButton", "Primary.TButton", "Danger.TButton"):   # same buttons on other surfaces
        s.configure(f"Bg.{base}", background=BG)
        s.configure(f"Banner.{base}", background=banner)
    s.configure("Link.TButton", padding=(S(6), S(3)))

    # check and radio buttons with drawn indicators
    for kind, radio in (("Checkbutton", False), ("Radiobutton", True)):
        el = f"Round.{kind}.indicator"
        s.element_create(el, "image", check_image(False, True, radio),
                         ("selected", "disabled", check_image(True, False, radio)),
                         ("disabled", check_image(False, False, radio)), ("selected", check_image(True, True, radio)),
                         padding=(0, 0, S(8), 0))
        layout = [(f"{kind}.padding", {"sticky": "nswe", "children": [
            (el, {"side": "left", "sticky": ""}), (f"{kind}.label", {"side": "left", "sticky": "nswe"})]})]
        for prefix, bg in (("", PANEL), ("Side.", SIDE)):
            st = f"{prefix}T{kind}"
            s.layout(st, layout)
            s.configure(st, background=bg, foreground=TEXT, padding=(0, S(2), S(4), S(2)))
            s.map(st, background=[("active", bg)], foreground=[("disabled", MUTED)])

    s.element_create("Segment.bg", "image", box(PANEL2, LINE), ("selected", box(ACCENT)),
                     ("active", box(HOVER, LINE)), border=r, sticky="nsew", padding=0, width=2 * r, height=2 * r)
    s.layout("Segment.TRadiobutton", [("Segment.bg", {"sticky": "nsew", "children": [
        ("Radiobutton.padding", {"sticky": "nsew", "children": [("Radiobutton.label", {"sticky": "nsew"})]})]})])
    s.configure("Segment.TRadiobutton", padding=(S(16), S(5)), background=PANEL, foreground=TEXT, anchor="center")
    s.map("Segment.TRadiobutton", foreground=[("selected", ON_ACCENT)], background=[("active", PANEL)])

    # text fields: rounded, accent outline when focused
    s.element_create("Round.field", "image", box(PANEL2, LINE, 6), ("disabled", box(PANEL, LINE, 6)),
                     ("focus", box(PANEL2, ACCENT, 6)), border=S(6) + 2, sticky="nsew", padding=0,
                     width=2 * S(6) + 4, height=2 * S(6) + 4)
    s.element_create("Round.arrow", "image", chevron(MUTED), sticky="", padding=(S(4), 0, S(10), 0))
    s.layout("TEntry", [("Round.field", {"sticky": "nswe", "children": [
        ("Entry.padding", {"sticky": "nswe", "children": [("Entry.textarea", {"sticky": "nswe"})]})]})])
    s.configure("TEntry", padding=(S(8), S(5)), foreground=TEXT, insertcolor=TEXT, background=PANEL)
    s.layout("TCombobox", [("Round.field", {"sticky": "nswe", "children": [
        ("Round.arrow", {"side": "right", "sticky": "ns"}),
        ("Combobox.padding", {"sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]})]})])
    s.configure("TCombobox", padding=(S(8), S(5)), foreground=TEXT, arrowsize=0, background=PANEL)
    s.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", PANEL2)], selectforeground=[("readonly", TEXT)])
    s.layout("TSpinbox", [("Round.field", {"sticky": "nswe", "children": [
        ("null", {"side": "right", "sticky": "ns", "children": [
            ("Spinbox.uparrow", {"side": "top", "sticky": "e"}), ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"})]}),
        ("Spinbox.padding", {"sticky": "nswe", "children": [("Spinbox.textarea", {"sticky": "nswe"})]})]})])
    s.configure("TSpinbox", padding=(S(8), S(4)), foreground=TEXT, arrowcolor=MUTED, arrowsize=S(10), background=PANEL,
                fieldbackground=PANEL2, bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2)
    s.map("TSpinbox", background=[("active", PANEL2)], arrowcolor=[("active", TEXT)])

    # slider: thin rounded track and a round thumb
    s.element_create("Round.trough", "image", box(PANEL2, LINE, 3), border=S(3) + 2, sticky="ew", padding=0,
                     width=2 * S(3) + 4, height=2 * S(3) + 4)
    s.element_create("Round.slider", "image", dot(ACCENT, 18, PANEL), ("active", dot(ACCENT_HOVER, 18, PANEL)), sticky="")
    s.layout("Horizontal.TScale", [("Round.trough", {"sticky": "ew", "children": [
        ("Round.slider", {"side": "left", "sticky": ""})]})])
    s.configure("Horizontal.TScale", background=PANEL)

    # device list and tables
    s.configure("Treeview", background=SIDE, fieldbackground=SIDE, foreground=TEXT, rowheight=S(40), borderwidth=0,
                indent=0, relief="flat")
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.layout("Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Treeitem.image", {"side": "left", "sticky": ""}), ("Treeitem.text", {"side": "left", "sticky": ""})]})])
    s.configure("Treeview.Item", padding=(S(10), 0, 0, 0))
    s.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    s.configure("Diag.Treeview", rowheight=S(24), background=PANEL, fieldbackground=PANEL)
    s.configure("Treeview.Heading", background=PANEL2, foreground=MUTED, relief="flat", borderwidth=0,
                font=(SMALL[0], 9, "bold"), padding=(S(8), S(5)))
    s.map("Treeview.Heading", background=[("active", HOVER)])
    # scrollbar: a slim pill thumb on the window background, no arrows; brighter on hover and drag
    tw, th = S(6), S(32)
    s.element_create("Round.thumb", "image", pill(mix(BG, TEXT, .2), tw, th), ("pressed", pill(mix(BG, TEXT, .5), tw, th)),
                     ("active", pill(mix(BG, TEXT, .35), tw, th)), border=(0, tw // 2 + 1), sticky="ns", padding=0)
    s.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Round.thumb", {"expand": "1", "sticky": "ns"})]})])
    s.configure("Vertical.TScrollbar", troughcolor=BG, background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                gripcount=0, troughrelief="flat", relief="flat", borderwidth=0)
    title_bar(root)
