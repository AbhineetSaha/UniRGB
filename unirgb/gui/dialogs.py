"""Settings (first start included), Scenes and Diagnostics windows."""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .. import system_setup
from . import theme as T


class Dialog(tk.Toplevel):
    def __init__(self, master, title: str, width: int = 620):
        super().__init__(master)
        self.title(title)
        self.configure(bg=T.PANEL)
        self.transient(master)
        self.resizable(True, True)
        self.minsize(T.S(width), T.S(200))
        self.body = ttk.Frame(self, style="Panel.TFrame", padding=(T.S(24), T.S(20)))
        self.body.pack(fill="both", expand=True)
        ttk.Label(self.body, text=title, style="Panel.TLabel", font=T.SUBTITLE).pack(anchor="w", pady=(0, T.S(8)))
        T.title_bar(self)
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(10, self._show)

    def _show(self):
        self.update_idletasks()
        m = self.master
        self.geometry(f"+{m.winfo_rootx() + max(0, (m.winfo_width() - self.winfo_width()) // 2)}"
                      f"+{m.winfo_rooty() + 60}")
        self.grab_set()
        self.focus_set()

    def text(self, parent, text, muted=True, wrap=560, **kw):
        lbl = ttk.Label(parent, text=text, style="Muted.TLabel" if muted else "Panel.TLabel", wraplength=wrap,
                        justify="left", **kw)
        lbl.pack(anchor="w", pady=(0, T.S(8)))
        return lbl


class SettingsDialog(Dialog):
    """Which features to use, and the one-time admin setup they need."""

    def __init__(self, win, first: bool, on_restart):
        super().__init__(win.root, "Welcome to UniRGB" if first else "Settings")
        self.win, self.app, self.on_restart = win, win.app, on_restart
        P = self.app.prefs.to_dict()
        self.text(self.body, "Lighting works right away. The other features need UniRGB's hardware driver (PawnIO). "
                             "Tick only what you want; you can change this later in Settings.")
        self.cpu = tk.BooleanVar(value=P["cpu_temperature"])
        self.ram = tk.BooleanVar(value=P["ram_lighting"])
        for text, var, chip, color, enabled in (
                ("Lighting for mouse, keyboard, motherboard and cooler", tk.BooleanVar(value=True), "No driver needed", T.OK, False),
                ("CPU temperature on the pump display", self.cpu, "Needs driver", T.WARN, True),
                ("RAM lighting", self.ram, "Needs driver" if P["available"]["ram_lighting"] else "Coming soon", T.WARN,
                 P["available"]["ram_lighting"])):
            r = ttk.Frame(self.body, style="Panel.TFrame")
            r.pack(fill="x", pady=T.S(5))
            cb = ttk.Checkbutton(r, text=text, variable=var)
            cb.pack(side="left")
            if not enabled:
                cb.state(["disabled"])
            ttk.Label(r, text=chip, style=T.chip_style(color, T.PANEL)).pack(side="right")
        if P["available"]["ram_lighting"]:
            self.text(self.body, "RAM lighting supports ENE controllers (for example G.Skill and other DDR5 kits) on AMD "
                                 "boards. Colors are never saved to the sticks.")
        self.status = ttk.Frame(self.body, style="Panel.TFrame")
        self.status.pack(fill="x", pady=(T.S(8), 0))
        r = ttk.Frame(self.body, style="Panel.TFrame")
        r.pack(fill="x", pady=(T.S(18), 0))
        ttk.Button(r, text="Continue" if first else "Save", style="Primary.TButton", command=self.save).pack(side="right")
        self.load_status()

    def load_status(self, then=None):
        def done(st):
            if not self.winfo_exists():
                return
            if isinstance(st, Exception):
                self.win.toast(str(st), "bad")
                return
            self._show_status(st)
            if then:
                then(st)
        self.win.bridge.run(lambda: system_setup.status(Path(sys.executable)), done)

    def _show_status(self, st):
        for w in self.status.winfo_children():
            w.destroy()
        p = self.app.prefs.prefs
        last = st.get("last_result") or {}
        fail = f" Last attempt failed: {last.get('error')}" if last and not last.get("ok") else ""
        if p.needs_driver and not st["ready"]:
            msg = ("UniRGB was updated, so its background helper needs refreshing." if st["stale"] else
                   "One-time setup: " + ("installs the PawnIO driver and " if st["driver"] == "not-installed" else "") +
                   "adds UniRGB's background helper. One Windows admin prompt now, none on later starts.") + fail
            self._banner(msg, "Set up now", lambda: self.run_setup(True))
        elif not p.needs_driver and (st["task"] or st["helper"]):
            self._banner("UniRGB's background helper is still installed but nothing uses it." + fail, "Remove it",
                         lambda: self.run_setup(False))
        elif p.needs_driver:
            ttk.Label(self.status, text="Background helper ready", style=T.chip_style(T.OK, T.PANEL)).pack(anchor="w")

    def _banner(self, text, button, command):
        b = ttk.Frame(self.status, style="Panel.Banner.TFrame", padding=(T.S(14), T.S(8)))
        b.pack(fill="x")
        ttk.Label(b, text=text, style="Banner.TLabel", wraplength=T.S(400), justify="left").pack(side="left", pady=T.S(4))
        ttk.Button(b, text=button, style="Banner.Primary.TButton", command=command).pack(side="right", padx=(T.S(10), 0))

    def save(self):
        try:
            self.app.prefs.update({"setup_done": True, "cpu_temperature": self.cpu.get(), "ram_lighting": self.ram.get()})
        except ValueError as e:
            self.win.toast(str(e), "bad")
            return
        self.win.toast("Settings saved", "ok")
        self.win.refresh()

        def next_step(st):   # keep the window open while a setup or removal is still needed
            p = self.app.prefs.prefs
            if not ((p.needs_driver and not st["ready"]) or (not p.needs_driver and (st["task"] or st["helper"]))):
                self.destroy()
        self.load_status(next_step)

    def run_setup(self, enable: bool):
        def started(res):
            if isinstance(res, Exception) or not res[0]:
                self.win.toast(str(res) if isinstance(res, Exception) else res[1], "bad")
                return
            self.win.toast(res[1])
            self._watch(enable, time.monotonic())
        self.win.bridge.run(lambda: system_setup.request(enable), started)

    def _watch(self, enable, t0):
        """The elevated setup runs on its own; check its result every 2 s for up to a minute."""
        def check(st):
            last = st.get("last_result") or {}
            if enable and st["ready"] and last.get("ok"):
                self.destroy()
                self.on_restart()
                return
            failed = enable and last and not last.get("ok") and last.get("at", 0) > time.time() - 60
            removed = not enable and not st["task"] and not st["helper"]
            if not (failed or removed) and time.monotonic() - t0 < 60:
                self.after(2000, lambda: self.winfo_exists() and self.load_status(check))
        self.after(2000, lambda: self.winfo_exists() and self.load_status(check))


class ScenesDialog(Dialog):
    def __init__(self, win):
        super().__init__(win.root, "Scenes", 560)
        self.win, self.app = win, win.app
        self.text(self.body, f"A scene saves the color you last asked for on each controllable device. "
                             f"Stored in {self.app.scenes.path}.")
        r = ttk.Frame(self.body, style="Panel.TFrame")
        r.pack(fill="x", pady=(T.S(4), T.S(12)))
        self.name = tk.StringVar()
        e = ttk.Entry(r, textvariable=self.name)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _e: self.save())
        ttk.Button(r, text="Save current", style="Primary.TButton", command=self.save).pack(side="left", padx=(T.S(8), 0))
        self.list = ttk.Frame(self.body, style="Panel.TFrame")
        self.list.pack(fill="both", expand=True)
        r = ttk.Frame(self.body, style="Panel.TFrame")
        r.pack(fill="x", pady=(T.S(14), 0))
        ttk.Button(r, text="Export JSON", command=self.export).pack(side="left")
        ttk.Button(r, text="Import JSON", command=self.import_).pack(side="left", padx=T.S(8))
        self.render()

    def render(self):
        for w in self.list.winfo_children():
            w.destroy()
        if self.app.scenes.load_error:
            self.text(self.list, self.app.scenes.load_error, muted=False)
        scenes = self.app.scenes.list()
        if not scenes:
            self.text(self.list, "No scenes yet.")
        for name in sorted(scenes):
            r = ttk.Frame(self.list, style="Panel.Card.TFrame", padding=(T.S(16), T.S(10)))
            r.pack(fill="x", pady=T.S(3))
            for st in list(scenes[name].values())[:6]:   # a peek at the scene's colors
                c = "#000000" if st.mode == "off" else (st.color.hex() if st.color else T.PANEL2)
                ttk.Label(r, image=T.box(c, T.mix(c, T.TEXT, .3), 4, 16), style="Panel.TLabel").pack(side="left", padx=(0, T.S(3)))
            ttk.Label(r, text=name, style="Panel.TLabel", font=T.CARD_TITLE).pack(side="left", padx=(T.S(8), 0))
            ttk.Label(r, text=f"  {len(scenes[name])} device(s)", style="Muted.TLabel").pack(side="left")
            ttk.Button(r, text="Delete", style="Danger.TButton", command=lambda n=name: self.delete(n)).pack(side="right")
            ttk.Button(r, text="Apply", command=lambda n=name: self.apply(n)).pack(side="right", padx=T.S(6))

    def save(self):
        name = self.name.get().strip()
        try:
            devices = {r.info.id: r.desired for r in self.app.orch.registry.snapshot() if r.desired}
            self.app.scenes.put(name, devices)
        except ValueError as e:
            self.win.toast(str(e), "bad")
            return
        self.win.toast(f'Saved "{name}"', "ok")
        self.name.set("")
        self.render()

    def apply(self, name):
        def done(results):
            if isinstance(results, Exception):
                self.win.toast(str(results), "bad")
                return
            bad = {d: r for d, r in results.items() if not r.ok}
            self.win.toast("Scene partly applied: " + "; ".join(f"{d}: {r.message}" for d, r in bad.items())
                           if bad else "Scene applied", "bad" if bad else "ok")
            self.win.drafts.clear()
            self.win._sig = None
            self.win.refresh()
        self.win.bridge.run(lambda: self.app.scenes.apply(name, self.app.orch), done)

    def delete(self, name):
        self.app.scenes.delete(name)
        self.render()

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile="unirgb-scenes.json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(self.app.scenes.serialize(), encoding="utf-8")
            self.win.toast(f"Exported to {path}", "ok")

    def import_(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            names = self.app.scenes.import_json(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.win.toast(str(e), "bad")
            return
        self.win.toast(f"Imported {len(names)} scene(s)", "ok")
        self.render()


class DiagnosticsDialog(Dialog):
    def __init__(self, win):
        super().__init__(win.root, "Diagnostics", 820)
        app = win.app
        ttk.Label(self.body, text="Adapters", style="CardTitle.TLabel").pack(anchor="w")
        t = self._table(("Adapter", "Up", "Detail", "Control path"), (110, 50, 260, 380), 7)
        for name, h in app.orch.health().items():
            t.insert("", "end", values=(name, "yes" if h.available else "no", h.detail,
                                        app.orch.adapters[name].control_path))
        ttk.Label(self.body, text="HID collections (query-only)", style="CardTitle.TLabel").pack(anchor="w", pady=(T.S(16), 0))
        if app.hid.error:
            self.text(self.body, app.hid.error, muted=False)
        t = self._table(("VID:PID", "MI", "Usage", "In/Out/Feat", "Manufacturer / product"), (90, 40, 90, 100, 470), 12)
        for i in app.hid.get():
            usage = f"{i.usage_page:04X}:{i.usage:04X}" if i.usage_page is not None else "?"
            t.insert("", "end", values=(i.vidpid, "" if i.interface_number is None else i.interface_number, usage,
                                        f"{i.input_len}/{i.output_len}/{i.feature_len}",
                                        " / ".join(x for x in (i.manufacturer, i.product) if x)))

    def _table(self, cols, widths, height):
        t = ttk.Treeview(self.body, columns=cols, show="headings", height=height, style="Diag.Treeview")
        for c, w in zip(cols, widths):
            t.heading(c, text=c)
            t.column(c, width=w, anchor="w")
        t.pack(fill="both", expand=True, pady=(T.S(6), 0))
        return t
