"""Colors and ttk styles for UniRGB's native window (dark theme, the same palette as the old web UI)."""
from __future__ import annotations

from tkinter import ttk

BG, PANEL, PANEL2, LINE = "#0e1014", "#161920", "#1c2029", "#262b36"
TEXT, MUTED, ACCENT = "#e7e9ee", "#8a91a1", "#7c6cff"
OK, WARN, BAD, INFO = "#3ecf8e", "#f2b84b", "#ff6b6b", "#6cb6ff"
FONT = ("Segoe UI", 10)
SMALL = ("Segoe UI", 9)
TITLE = ("Segoe UI Semibold", 16)
CARD_TITLE = ("Segoe UI Semibold", 9)
MONO = ("Consolas", 9)

SUPPORT_LABEL = {"supported": "Supported", "experimental": "Experimental", "untested": "Untested",
                 "blocked": "Blocked", "unsupported": "Not available"}
SUPPORT_COLOR = {"supported": OK, "experimental": WARN, "untested": WARN, "blocked": BAD, "unsupported": MUTED}
CONNECTION = {"connected": ("Connected", OK), "monitor-only": ("Monitor only", INFO), "unavailable": ("Unavailable", MUTED),
              "asleep": ("Asleep", INFO), "error": ("Error", BAD)}


def apply(root) -> None:
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL2, bordercolor=LINE,
                lightcolor=LINE, darkcolor=LINE, troughcolor=PANEL2, focuscolor=ACCENT, font=FONT)
    s.configure("TFrame", background=BG)
    s.configure("Panel.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Panel.TLabel", background=PANEL)
    s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=SMALL)
    s.configure("MutedBg.TLabel", background=BG, foreground=MUTED, font=SMALL)
    s.configure("Title.TLabel", background=BG, font=TITLE)
    s.configure("CardTitle.TLabel", background=PANEL, foreground=MUTED, font=CARD_TITLE)
    s.configure("TButton", background=PANEL2, foreground=TEXT, padding=(12, 5), borderwidth=1)
    s.map("TButton", background=[("active", LINE), ("disabled", PANEL)], foreground=[("disabled", MUTED)])
    s.configure("Primary.TButton", background=ACCENT, foreground="#ffffff")
    s.map("Primary.TButton", background=[("active", "#6a5af0"), ("disabled", PANEL2)])
    s.configure("Danger.TButton", foreground=BAD)
    s.configure("TCheckbutton", background=PANEL, foreground=TEXT, indicatorbackground=PANEL2)
    s.map("TCheckbutton", background=[("active", PANEL)], indicatorbackground=[("selected", ACCENT)])
    s.configure("TRadiobutton", background=PANEL, foreground=TEXT, indicatorbackground=PANEL2)
    s.map("TRadiobutton", background=[("active", PANEL)], indicatorbackground=[("selected", ACCENT)])
    s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT, arrowcolor=TEXT)
    s.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", PANEL2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    s.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT)
    s.configure("TSpinbox", fieldbackground=PANEL2, foreground=TEXT, arrowcolor=TEXT)
    s.configure("Horizontal.TScale", background=PANEL, troughcolor=PANEL2)
    s.configure("Treeview", background=BG, fieldbackground=BG, foreground=TEXT, rowheight=40, borderwidth=0)
    s.map("Treeview", background=[("selected", PANEL2)], foreground=[("selected", TEXT)])
    s.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=BG, arrowcolor=MUTED)
