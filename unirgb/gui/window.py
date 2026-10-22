"""The main window: device list on the left, the selected device's page on the right."""
from __future__ import annotations

import re
import time
import tkinter as tk
from tkinter import colorchooser, ttk

from ..core.models import Color, LightingState
from . import theme as T

PRESETS = ["#ff3b30", "#ff9500", "#ffd60a", "#34c759", "#00c7be", "#0a84ff", "#5e5ce6", "#bf5af2", "#ffffff", "#000000"]
WRITABLE_LEVELS = ("supported", "experimental", "untested")
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def group_of(rec) -> str:
    if rec.connection.value in ("unavailable", "error"):
        return "Unavailable"
    if (rec.caps.writable or rec.caps.display.value == "supported") and not rec.shadowed_by:
        return "Controllable"
    return "Monitor only"


def current_color(rec) -> str | None:
    s = rec.confirmed or rec.desired
    if not s:
        return None
    return "#000000" if s.mode == "off" else (s.color.hex() if s.color else None)


class ScrollFrame(ttk.Frame):
    """A vertically scrolling area; put content into .inner."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=T.BG, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, e):
        w = e.widget
        while w is not None:   # scroll only when the pointer is over this area
            if w is self.canvas:
                self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
                return
            w = getattr(w, "master", None)

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


def card(parent, title: str) -> ttk.Frame:
    outer = tk.Frame(parent, bg=T.PANEL, highlightbackground=T.LINE, highlightthickness=1)
    ttk.Label(outer, text=title.upper(), style="CardTitle.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
    body = ttk.Frame(outer, style="Panel.TFrame")
    body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
    outer.body = body
    return outer


def row(body, label: str) -> ttk.Frame:
    f = ttk.Frame(body, style="Panel.TFrame")
    f.pack(fill="x", pady=3)
    ttk.Label(f, text=label, style="Panel.TLabel", width=13, foreground=T.MUTED).pack(side="left")
    return f


def swatch(parent, color: str, size: int = 22, command=None, bg=T.PANEL) -> tk.Frame:
    f = tk.Frame(parent, width=size, height=size, bg=color, highlightbackground=T.LINE, highlightthickness=1,
                 cursor="hand2" if command else "")
    if command:
        f.bind("<Button-1>", lambda e: command())
    return f


class MainWindow:
    def __init__(self, root, app, bridge, version: str, on_quit, open_settings, open_scenes, open_diagnostics):
        self.root, self.app, self.bridge = root, app, bridge
        self.on_quit, self.open_settings = on_quit, open_settings
        self.sel: str | None = None
        self.drafts: dict[str, dict] = {}
        self.live = tk.BooleanVar(value=True)
        self.show_dupes = tk.BooleanVar(value=False)
        self._images: dict[str, tk.PhotoImage] = {}
        self._sig = None
        self._inflight, self._queued, self._send_after = False, False, None
        self._status_after = None
        self._state_box = None
        self._display_box = None

        root.title("UniRGB")
        root.geometry("1180x780")
        root.minsize(900, 560)
        T.apply(root)

        head = ttk.Frame(root, padding=(16, 10))
        head.pack(fill="x")
        ttk.Label(head, text="UniRGB", font=("Segoe UI Semibold", 14)).pack(side="left")
        ttk.Label(head, text=f"v{version}", style="MutedBg.TLabel").pack(side="left", padx=(6, 0), pady=(4, 0))
        for text, cmd, style in (("Quit", on_quit, "Danger.TButton"), ("Rescan", self.rescan, "TButton"),
                                 ("Diagnostics", open_diagnostics, "TButton"), ("Settings", lambda: open_settings(False), "TButton"),
                                 ("Scenes", open_scenes, "TButton")):
            ttk.Button(head, text=text, command=cmd, style=style).pack(side="right", padx=(6, 0))
        ttk.Button(head, text="Sync all", command=self.sync_all).pack(side="right", padx=(12, 0))
        self.sync_color = "#7c6cff"
        self._sync_sw = swatch(head, self.sync_color, 26, self._pick_sync, bg=T.BG)
        self._sync_sw.pack(side="right")
        ttk.Label(head, text="All controllable", style="MutedBg.TLabel").pack(side="right", padx=(0, 8))

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, width=290)
        side.pack(side="left", fill="y", padx=(12, 0))
        side.pack_propagate(False)
        self.tree = ttk.Treeview(side, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.tag_configure("group", foreground=T.MUTED, font=T.CARD_TITLE)
        self.tree.tag_configure("dupe", foreground=T.MUTED)
        ttk.Checkbutton(side, text="Show duplicate entries", variable=self.show_dupes, style="TCheckbutton",
                        command=self.refresh).pack(anchor="w", pady=6)
        self.detail = ScrollFrame(body)
        self.detail.pack(side="left", fill="both", expand=True, padx=12)

        foot = ttk.Frame(root, padding=(16, 6))
        foot.pack(fill="x")
        self.health = ttk.Frame(foot)
        self.health.pack(side="left")
        self.status = ttk.Label(foot, text="", style="MutedBg.TLabel")
        self.status.pack(side="right")

        self.refresh()
        root.after(2000, self._tick)

    # ---------- helpers ----------
    def toast(self, msg: str, kind: str = "info") -> None:
        color = {"ok": T.OK, "bad": T.BAD, "info": T.MUTED}[kind]
        self.status.configure(text=msg, foreground=color)
        if self._status_after:
            self.root.after_cancel(self._status_after)
        self._status_after = self.root.after(8000 if kind == "bad" else 4000, lambda: self.status.configure(text=""))

    def _img(self, color: str, size: int = 14) -> tk.PhotoImage:
        if color not in self._images:
            img = tk.PhotoImage(width=size, height=size)
            img.put(color, to=(0, 0, size, size))
            self._images[color] = img
        return self._images[color]

    def records(self):
        return self.app.orch.registry.snapshot()

    def record(self, dev_id):
        return self.app.orch.registry.get(dev_id)

    def _tick(self):
        if not self._inflight:
            self.refresh()
        self.root.after(2000, self._tick)

    # ---------- refresh ----------
    def refresh(self) -> None:
        recs = self.records()
        if not self.sel or not any(r.info.id == self.sel for r in recs):
            ctl = [r for r in recs if r.caps.writable and r.connection.value == "connected" and not r.shadowed_by]
            first = next((r for r in ctl if r.caps.color.value == "supported" and r.info.adapter != "sim"), None) \
                or (ctl[0] if ctl else (recs[0] if recs else None))
            self.sel = first.info.id if first else None
        self._fill_tree(recs)
        self._fill_health()
        rec = self.record(self.sel) if self.sel else None
        sig = rec and (rec.info.id, rec.connection, rec.caps.writable, rec.shadowed_by, rec.caps.display,
                       tuple(rec.info.controlled_by), len(rec.caps.notes))
        if sig != self._sig:
            self._sig = sig
            self.render_detail()
        elif rec and self._state_box is not None and self._state_box.winfo_exists():
            self._fill_state(self._state_box, rec)

    def _fill_tree(self, recs):
        self.tree.delete(*self.tree.get_children())
        groups = {"Controllable": [], "Monitor only": [], "Unavailable": []}
        for r in recs:
            if self.show_dupes.get() or not r.shadowed_by:
                groups[group_of(r)].append(r)
        for g, items in groups.items():
            if not items:
                continue
            gid = f"grp:{g}"
            self.tree.insert("", "end", iid=gid, text=f"{g.upper()}   {len(items)}", open=True, tags=("group",))
            for r in items:
                color = current_color(r) or T.CONNECTION[r.connection.value][1]
                self.tree.insert(gid, "end", iid=r.info.id, text=f"  {r.info.name}", image=self._img(color),
                                 tags=("dupe",) if r.shadowed_by else ())
        if self.sel and self.tree.exists(self.sel):
            self.tree.selection_set(self.sel)

    def _fill_health(self):
        for w in self.health.winfo_children():
            w.destroy()
        for name, h in self.app.orch.health().items():
            ttk.Label(self.health, text=f"● {name}", style="MutedBg.TLabel",
                      foreground=T.OK if h.available else T.MUTED).pack(side="left", padx=(0, 10))
        t = time.strftime("%H:%M:%S", time.localtime(self.app.last_scan)) if self.app.last_scan else "—"
        ttk.Label(self.health, text=f"last scan {t} ({round(self.app.last_scan_ms)} ms)",
                  style="MutedBg.TLabel").pack(side="left", padx=(10, 0))

    def _on_select(self, _e=None):
        s = self.tree.selection()
        if s and not s[0].startswith("grp:") and s[0] != self.sel:
            self.sel = s[0]
            self._sig = None
            self.refresh()

    # ---------- device page ----------
    def render_detail(self) -> None:
        self.detail.clear()
        self._state_box = self._display_box = None
        rec = self.record(self.sel) if self.sel else None
        page = self.detail.inner
        if rec is None:
            ttk.Label(page, text="No devices found.", style="MutedBg.TLabel").pack(pady=40)
            return
        if rec.info.adapter == "sim":
            self._banner(page, "Simulated device. Nothing here touches real hardware.")
        head = ttk.Frame(page)
        head.pack(fill="x", pady=(8, 10))
        ttk.Label(head, text=rec.info.name, font=T.TITLE).pack(anchor="w")
        chips = ttk.Frame(head)
        chips.pack(anchor="w", pady=(4, 0))
        label, color = T.CONNECTION[rec.connection.value]
        bits = [(label, color)] + [(t, T.MUTED) for t in (rec.info.vendor, rec.info.vidpid, rec.info.category.value,
                                                          f"adapter: {rec.info.adapter}") if t]
        if rec.caps.color.value in ("experimental", "untested"):
            bits.append((f"{rec.caps.color.value} control", T.WARN))
        if rec.shadowed_by:
            bits.append((f"duplicate of {rec.shadowed_by}", T.WARN))
        for text, c in bits:
            tk.Label(chips, text=text, bg=T.BG, fg=c, font=T.SMALL, highlightbackground=T.LINE, highlightthickness=1,
                     padx=8, pady=1).pack(side="left", padx=(0, 6))
        if any("controlling the lighting" in c for c in rec.info.controlled_by):
            b = self._banner(page, "Razer Synapse is controlling this mouse's lighting, so UniRGB cannot reach it.")
            ttk.Button(b, text="Quit Razer Synapse", style="Primary.TButton",
                       command=lambda: self._quit_synapse(rec.info.id)).pack(side="right")

        grid = ttk.Frame(page)
        grid.pack(fill="both", expand=True)
        cards = [self._controls_card(grid, rec)]
        if rec.info.adapter == "razer-hid" and rec.connection.value == "connected":
            cards.append(self._mouse_card(grid, rec))
        if rec.caps.writable and not rec.shadowed_by:
            c = card(grid, "State")
            self._state_box = c.body
            self._fill_state(c.body, rec)
            cards.append(c)
        cards += [self._caps_card(grid, rec), self._info_card(grid, rec)]
        for i, c in enumerate(cards):
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 12), pady=(0, 12))
        grid.columnconfigure((0, 1), weight=1, uniform="col")

    def _banner(self, parent, text) -> tk.Frame:
        b = tk.Frame(parent, bg="#2a2416", highlightbackground="#5c4a1e", highlightthickness=1)
        b.pack(fill="x", pady=(8, 0))
        tk.Label(b, text=text, bg="#2a2416", fg=T.TEXT, wraplength=620, justify="left").pack(side="left", padx=12, pady=8)
        return b

    # --- lighting ---
    def _draft(self, rec) -> dict:
        if rec.info.id not in self.drafts:
            s = rec.desired
            self.drafts[rec.info.id] = {"mode": s.mode if s else "static", "color": s.color.hex() if s and s.color else "#7c6cff",
                                        "brightness": s.brightness if s else 100,
                                        "zones": {k: c.hex() for k, c in (s.zones if s else {}).items()}}
        return self.drafts[rec.info.id]

    def _controls_card(self, parent, rec):
        caps = rec.caps
        if caps.display.value == "supported" and not rec.shadowed_by:
            return self._display_card(parent, rec)
        c = card(parent, "Lighting" if caps.writable and not rec.shadowed_by else "Control")
        b = c.body
        if rec.shadowed_by:
            ttk.Label(b, text=f"This hardware is controlled through {rec.shadowed_by}. Use that entry instead.",
                      style="Muted.TLabel", wraplength=380).pack(anchor="w")
            return c
        if not caps.writable:
            ttk.Label(b, text="Read-only. UniRGB has no verified, safe way to write to this device. "
                              "The reasons are listed under Details.", style="Muted.TLabel", wraplength=380).pack(anchor="w")
            return c
        d = self._draft(rec)
        enabled = rec.connection.value == "connected"
        if len(caps.effects) > 1:
            r = row(b, "Mode")
            mode = tk.StringVar(value=d["mode"])
            for e in caps.effects:
                ttk.Radiobutton(r, text=e.capitalize(), value=e, variable=mode,
                                command=lambda: (d.__setitem__("mode", mode.get()), self._schedule(rec, now=True))
                                ).pack(side="left", padx=(0, 10))
        r = row(b, "Color")
        self._color_sw = swatch(r, d["color"], 28, lambda: self._pick(rec))
        self._color_sw.pack(side="left")
        self._hex = tk.StringVar(value=d["color"])
        e = ttk.Entry(r, textvariable=self._hex, width=9, font=T.MONO)
        e.pack(side="left", padx=8)
        e.bind("<Return>", lambda _e: self._hex_entered(rec))
        e.bind("<FocusOut>", lambda _e: self._hex_entered(rec))
        r = row(b, "")
        for p in PRESETS:
            swatch(r, p, 18, lambda p=p: self._set_color(rec, p)).pack(side="left", padx=(0, 4))
        if caps.brightness.value in WRITABLE_LEVELS:
            r = row(b, "Brightness")
            val = ttk.Label(r, text=f"{d['brightness']}%", style="Panel.TLabel", width=5)
            scale = ttk.Scale(r, from_=0, to=100, value=d["brightness"],
                              command=lambda v: (d.__setitem__("brightness", int(float(v))),
                                                 val.configure(text=f"{int(float(v))}%"), self._schedule(rec)))
            scale.pack(side="left", fill="x", expand=True)
            val.pack(side="left", padx=(8, 0))
            if not caps.brightness_native:
                ttk.Label(b, text="Done by scaling the color. This control path has no hardware brightness.",
                          style="Muted.TLabel").pack(anchor="w")
        if caps.zones and caps.zone_control.value in WRITABLE_LEVELS:
            ttk.Label(b, text=f"Zones ({T.SUPPORT_LABEL[caps.zone_control.value]}). Unticked zones use the main color.",
                      style="Muted.TLabel").pack(anchor="w", pady=(10, 2))
            for z in caps.zones:
                zr = ttk.Frame(b, style="Panel.TFrame")
                zr.pack(fill="x", pady=2)
                on = tk.BooleanVar(value=z.id in d["zones"])
                zsw = swatch(zr, d["zones"].get(z.id, d["color"]), 18)

                def toggle(z=z, on=on, zsw=zsw):
                    if on.get():
                        d["zones"][z.id] = zsw.cget("bg")
                    else:
                        d["zones"].pop(z.id, None)
                    self._schedule(rec)

                def pick_zone(z=z, on=on, zsw=zsw):
                    got = colorchooser.askcolor(color=zsw.cget("bg"), parent=self.root, title=z.name)[1]
                    if got:
                        zsw.configure(bg=got)
                        on.set(True)
                        d["zones"][z.id] = got
                        self._schedule(rec)
                ttk.Checkbutton(zr, text=z.name + (f" ({z.led_count})" if z.led_count > 1 else ""), variable=on,
                                command=toggle).pack(side="left")
                zsw.configure(cursor="hand2")
                zsw.bind("<Button-1>", lambda e, f=pick_zone: f())
                zsw.pack(side="right")
        r = ttk.Frame(b, style="Panel.TFrame")
        r.pack(fill="x", pady=(14, 0))
        ttk.Checkbutton(r, text="Live", variable=self.live).pack(side="left")
        apply_btn = ttk.Button(r, text="Apply", style="Primary.TButton", command=lambda: self._schedule(rec, now=True))
        apply_btn.pack(side="left", padx=10)
        if caps.restore.value in ("supported", "experimental"):
            ttk.Button(r, text="Restore" if rec.info.adapter == "sim" else "Return to vendor app", style="Danger.TButton",
                       command=lambda: self._restore(rec)).pack(side="left")
        if not enabled:
            apply_btn.state(["disabled"])
        return c

    def _pick(self, rec):
        got = colorchooser.askcolor(color=self._draft(rec)["color"], parent=self.root, title="Color")[1]
        if got:
            self._set_color(rec, got)

    def _hex_entered(self, rec):
        v = self._hex.get().strip()
        if HEX.match(v):
            self._set_color(rec, ("#" + v.lstrip("#")).lower())
        else:
            self.toast("Use a hex color like #33aaff", "bad")

    def _set_color(self, rec, color: str):
        d = self._draft(rec)
        d["color"] = color
        self._color_sw.configure(bg=color)
        self._hex.set(color)
        self._schedule(rec)

    def _schedule(self, rec, now: bool = False):
        if not now and not self.live.get():
            return
        if self._send_after:
            self.root.after_cancel(self._send_after)
        self._send_after = self.root.after(0 if now else 60, lambda: self._send(rec.info.id))

    def _send(self, dev_id: str):
        if self._inflight:
            self._queued = True
            return
        rec = self.record(dev_id)
        if rec is None:
            return
        d = self._draft(rec)
        bri = d["brightness"] if rec.caps.brightness.value in WRITABLE_LEVELS else 100
        try:
            state = LightingState(mode=d["mode"], color=Color.parse(d["color"]), brightness=bri,
                                  zones={k: Color.parse(v) for k, v in d["zones"].items()})
        except ValueError as e:
            self.toast(str(e), "bad")
            return
        self._inflight = True

        def done(res):
            self._inflight = False
            if isinstance(res, Exception) or not res.ok:
                self.toast(f"{rec.info.name}: {res if isinstance(res, Exception) else res.message}", "bad")
            if self._queued:
                self._queued = False
                self._send(dev_id)
            else:
                self.refresh()
        self.bridge.run(lambda: self.app.orch.apply(dev_id, state), done)

    def _restore(self, rec):
        def done(res):
            ok = not isinstance(res, Exception) and res.ok
            self.toast(str(res) if isinstance(res, Exception) else (res.message or ("Restored" if ok else "Restore failed")),
                       "ok" if ok else "bad")
            for k in [k for k in self.drafts if k.startswith(rec.info.adapter + ":")]:
                del self.drafts[k]
            self._sig = None
            self.refresh()
        self.bridge.run(lambda: self.app.orch.restore(rec.info.id), done)

    def _fill_state(self, box, rec):
        for w in box.winfo_children():
            w.destroy()
        if not rec.desired and not rec.confirmed and not rec.last_error:
            ttk.Label(box, text="No color set from UniRGB right now. Pick one, and what you asked for and what the "
                                "device confirmed appear here.", style="Muted.TLabel", wraplength=380).pack(anchor="w")
            return

        def show(label, s):
            r = row(box, label)
            if not s:
                ttk.Label(r, text="—", style="Muted.TLabel").pack(side="left")
                return
            swatch(r, "#000000" if s.mode == "off" else (s.color.hex() if s.color else T.PANEL2), 28).pack(side="left")
            extra = f" · zones: {', '.join(f'{k} {c.hex()}' for k, c in s.zones.items())}" if s.zones else ""
            ttk.Label(r, text=f"  {s.mode}{' · ' + s.color.hex() if s.color else ''} · brightness {s.brightness}%{extra}",
                      style="Panel.TLabel").pack(side="left")
        show("Requested", rec.desired)
        show("Confirmed", rec.confirmed)
        conf = {"hardware-readback": ("Read back from hardware", T.OK), "api-accepted": ("Accepted by vendor API (LEDs not observed)", T.WARN),
                "device-ack": ("Acknowledged by the device", T.OK), "none": ("Not confirmed", T.MUTED)}
        text, color = conf.get(rec.confirmation.value, (rec.confirmation.value, T.MUTED))
        if rec.info.adapter == "sim" and rec.confirmation.value == "hardware-readback":
            text, color = "Simulated read-back", T.WARN
        ttk.Label(row(box, ""), text=text, style="Panel.TLabel", foreground=color).pack(side="left")
        if rec.last_error:
            ttk.Label(row(box, "Last error"), text=rec.last_error, style="Panel.TLabel", foreground=T.BAD,
                      wraplength=320).pack(side="left")

    # --- capabilities / details ---
    def _caps_card(self, parent, rec):
        c = card(parent, "Capabilities")
        caps = rec.caps
        for label, v in (("Discovery", caps.discovery), ("Display", caps.display), ("Read state", caps.read_state),
                         ("Color", caps.color), ("Brightness", caps.brightness), ("Zones", caps.zone_control),
                         ("Fan control", caps.fan_control), ("Restore", caps.restore)):
            ttk.Label(row(c.body, label), text=T.SUPPORT_LABEL[v.value], style="Panel.TLabel",
                      foreground=T.SUPPORT_COLOR[v.value]).pack(side="left")
        ttk.Label(row(c.body, "Effects"), text=", ".join(caps.effects) or "—", style="Panel.TLabel").pack(side="left")
        return c

    def _info_card(self, parent, rec):
        c = card(parent, "Details")
        i = rec.info
        for label, text in (("Control path", i.connection_path or "—"), ("Owned by", ", ".join(i.controlled_by) or "—"),
                            ("Device id", i.id)):
            ttk.Label(row(c.body, label), text=text, style="Panel.TLabel", wraplength=330, justify="left",
                      font=T.MONO if label != "Owned by" else T.FONT).pack(side="left")
        more = ttk.Frame(c.body, style="Panel.TFrame")

        def toggle():
            if more.winfo_ismapped():
                more.pack_forget()
            else:
                more.pack(fill="x", pady=(6, 0))
        ttk.Button(c.body, text=f"Evidence and notes ({len(i.evidence) + len(rec.caps.notes)})",
                   command=toggle).pack(anchor="w", pady=(8, 0))
        for title, items in (("Evidence", i.evidence), ("Notes", rec.caps.notes)):
            ttk.Label(more, text=title.upper(), style="CardTitle.TLabel").pack(anchor="w", pady=(8, 2))
            for t in items or ["—"]:
                ttk.Label(more, text="•  " + t, style="Panel.TLabel", wraplength=400, justify="left").pack(anchor="w")
        return c

    # --- pump display ---
    def _display_card(self, parent, rec):
        c = card(parent, "Temperature display")
        self._display_box = c.body
        ttk.Label(c.body, text="Loading…", style="Muted.TLabel").pack(anchor="w")
        self._load_display(rec.info.id, rebuild=True)
        return c

    def _load_display(self, dev_id, rebuild=False):
        def done(s):
            box = self._display_box
            if box is None or not box.winfo_exists() or self.sel != dev_id or isinstance(s, Exception) or not s.get("settings"):
                return
            if rebuild:
                self._build_display(box, dev_id, s)
            else:
                self._update_display(s)
            self.root.after(2000, lambda: self._display_box is box and box.winfo_exists() and self._load_display(dev_id))
        self.bridge.run(lambda: self.app.orch.status(dev_id), done)

    def _reading_text(self, s):
        last = s.get("last") or {}
        r = last.get("reading")
        line1 = f"{r['label']}: {r['celsius']} °C" if r else "No reading yet"
        line2 = last.get("error") or (("sent " + time.strftime("%H:%M:%S", time.localtime(last["at"]))) if last.get("at") else "")
        return str(last.get("sent", "--")), line1, line2, bool(last.get("error"))

    def _cpu_source(self, s):
        r = (s.get("last") or {}).get("reading") or {}
        if r.get("source") == "cpu-pawnio":
            return "UniRGB hardware helper", T.OK, False
        if self.app.prefs.prefs.cpu_temperature:
            return "UniRGB hardware helper not answering", T.WARN, True
        if s["lhm"]["running"]:
            return "LibreHardwareMonitor connected", T.OK, False
        return "Not available: turn on CPU temperature in Settings", T.WARN, True

    def _update_display(self, s):
        sent, l1, l2, err = self._reading_text(s)
        self._disp_big.configure(text=sent)
        self._disp_l1.configure(text=l1)
        self._disp_l2.configure(text=l2, foreground=T.BAD if err else T.MUTED)
        text, color, _ = self._cpu_source(s)
        self._disp_src.configure(text=text, foreground=color)

    def _build_display(self, box, dev_id, s):
        for w in box.winfo_children():
            w.destroy()
        st = s["settings"]

        def send(body):
            def done(res):
                if isinstance(res, Exception) or not res.ok:
                    self.toast(str(res) if isinstance(res, Exception) else res.message, "bad")
                self._load_display(dev_id, rebuild=True)
            self.bridge.run(lambda: self.app.orch.configure(dev_id, body), done)

        top = ttk.Frame(box, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 8))
        self._disp_big = tk.Label(top, text="--", bg=T.PANEL2, fg=T.TEXT, font=("Consolas", 18, "bold"), width=4, pady=6)
        self._disp_big.pack(side="left")
        txt = ttk.Frame(top, style="Panel.TFrame")
        txt.pack(side="left", padx=10)
        self._disp_l1 = ttk.Label(txt, text="", style="Panel.TLabel")
        self._disp_l1.pack(anchor="w")
        self._disp_l2 = ttk.Label(txt, text="", style="Muted.TLabel")
        self._disp_l2.pack(anchor="w")
        if not st["confirmed"]:
            b = self._banner(box, "UniRGB has not sent anything to this USB device yet. Its chip (5131:2007) is also "
                                  "used by relay boards and other gadgets.")
            ttk.Button(b, text="Yes, this is my cooler display", style="Primary.TButton",
                       command=lambda: send({"confirmed": True})).pack(side="right", padx=8)
        en = tk.BooleanVar(value=st["enabled"])
        ttk.Checkbutton(row(box, "Display"), text="On", variable=en, command=lambda: send({"enabled": en.get()})).pack(side="left")
        src = {"auto": "Auto (CPU if available, else GPU)", "cpu": "CPU only", "gpu": "GPU only"}
        self._combo(row(box, "Source"), src, st["source"], lambda v: send({"source": v}))
        unit = tk.StringVar(value="f" if st["fahrenheit"] else "c")
        r = row(box, "Unit")
        for v, t in (("c", "°C"), ("f", "°F")):
            ttk.Radiobutton(r, text=t, value=v, variable=unit, command=lambda: send({"fahrenheit": unit.get() == "f"})
                            ).pack(side="left", padx=(0, 10))
        ab = {"cap84": "Hold at 84 (no flashing)", "compress": "Compress 75–100 into 75–84", "raw": "Raw (panel flashes at 85+)"}
        self._combo(row(box, "Above 84 °C"), ab, st["anti_blink"], lambda v: send({"anti_blink": v}))
        r = row(box, "CPU source")
        text, color, needs_settings = self._cpu_source(s)
        self._disp_src = ttk.Label(r, text=text, style="Panel.TLabel", foreground=color, wraplength=260)
        self._disp_src.pack(side="left")
        if needs_settings:
            ttk.Button(r, text="Open Settings", command=lambda: self.open_settings(False)).pack(side="left", padx=8)
        for f in s["lhm"]["fans"]:
            ttk.Label(row(box, "Fan"), text=f"{f['name']}: {f['rpm']} RPM", style="Panel.TLabel").pack(side="left")
        own = ((s.get("last") or {}).get("reading") or {}).get("source") == "cpu-pawnio"
        amd = s.get("cpu_helper") or {}
        if not own and not s["lhm"]["running"] and amd.get("amd_cli_installed") and not amd.get("running"):
            adapter = self.app.orch.adapters.get(self.record(dev_id).info.adapter)

            def start_amd():   # optional, proprietary SDK installed separately; one UAC prompt
                self.bridge.run(adapter.start_cpu_helper, lambda res: self.toast(
                    str(res) if isinstance(res, Exception) else res.message,
                    "ok" if not isinstance(res, Exception) and res.ok else "bad"))
            ttk.Button(box, text="Use AMD Ryzen Master instead (admin prompt)", command=start_amd).pack(anchor="w", pady=(10, 0))
        self._update_display(s)

    def _combo(self, parent, choices: dict, current, on_change):
        var = tk.StringVar(value=choices.get(current, current))
        cb = ttk.Combobox(parent, values=list(choices.values()), textvariable=var, state="readonly", width=30)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: on_change(next(k for k, v in choices.items() if v == var.get())))
        return cb

    # --- mouse ---
    def _mouse_card(self, parent, rec):
        c = card(parent, "Mouse settings")
        ttk.Label(c.body, text="Reading from the mouse…", style="Muted.TLabel").pack(anchor="w")
        dev_id = rec.info.id

        def done(s):
            if not c.body.winfo_exists():
                return
            for w in c.body.winfo_children():
                w.destroy()
            if isinstance(s, Exception) or not s.get("mouse"):
                ttk.Label(c.body, text=str(s) if isinstance(s, Exception) else s.get("error", "Mouse not answering"),
                          style="Muted.TLabel", wraplength=380).pack(anchor="w")
                return
            self._build_mouse(c.body, dev_id, s)
        self.bridge.run(lambda: self.app.orch.status(dev_id), done)
        return c

    def _build_mouse(self, box, dev_id, s):
        m = s["mouse"]
        ttk.Label(row(box, "Battery"), text=f"{m['battery_pct']}%" + (" · charging" if m["charging"] else "")
                  + f"  (warns at {m['low_battery_pct']}%)", style="Panel.TLabel").pack(side="left")
        active = tk.IntVar(value=m["active_stage"])
        dpis = []
        for i, st in enumerate(m["stages"]):
            r = row(box, "DPI stages" if i == 0 else "")
            ttk.Radiobutton(r, text=str(i + 1), value=i + 1, variable=active).pack(side="left")
            v = tk.StringVar(value=str(st[0]))
            ttk.Spinbox(r, from_=100, to=30000, increment=50, textvariable=v, width=8).pack(side="left", padx=8)
            dpis.append(v)
        ttk.Label(box, text=f"Current DPI: {m['dpi'][0]}" + (f" × {m['dpi'][1]}" if m["dpi"][1] != m["dpi"][0] else ""),
                  style="Muted.TLabel").pack(anchor="w")
        poll = {str(h): f"{h} Hz" for h in s["poll_choices"]}
        poll_v = tk.StringVar(value=str(m["poll_hz"]))
        self._combo(row(box, "Polling"), poll, str(m["poll_hz"]), poll_v.set)
        idle = {str(v): f"{v // 60} min" for v in (60, 120, 180, 300, 600, 900)}
        idle.setdefault(str(m["idle_s"]), f"{m['idle_s']} s")
        idle_v = tk.StringVar(value=str(m["idle_s"]))
        self._combo(row(box, "Sleep after"), idle, str(m["idle_s"]), idle_v.set)

        def post(body):
            def done(res):
                ok = not isinstance(res, Exception) and res.ok
                self.toast(str(res) if isinstance(res, Exception) else res.message, "ok" if ok else "bad")
                self._sig = None
                self.refresh()
            self.bridge.run(lambda: self.app.orch.configure(dev_id, body), done)

        def save():
            try:
                stages = [[int(v.get()), int(v.get())] for v in dpis]
            except ValueError:
                self.toast("DPI values must be numbers", "bad")
                return
            post({"stages": stages, "active_stage": active.get(), "poll_hz": int(poll_v.get()), "idle_s": int(idle_v.get())})
        r = ttk.Frame(box, style="Panel.TFrame")
        r.pack(fill="x", pady=(14, 0))
        ttk.Button(r, text="Save to mouse", style="Primary.TButton", command=save).pack(side="left")
        ttk.Button(r, text="Restore originals", style="Danger.TButton",
                   command=lambda: post({"restore_baseline": True})).pack(side="left", padx=8)

    # ---------- header actions ----------
    def _pick_sync(self):
        got = colorchooser.askcolor(color=self.sync_color, parent=self.root, title="Color for every device")[1]
        if got:
            self.sync_color = got
            self._sync_sw.configure(bg=got)

    def sync_all(self):
        targets = [r for r in self.records() if r.caps.writable and not r.shadowed_by and r.connection.value == "connected"]
        if not targets:
            self.toast("No controllable devices", "bad")
            return
        color = self.sync_color

        def work():
            out = []
            for r in targets:
                d = self._draft(r)
                d.update(mode="static", color=color, zones={})
                bri = d["brightness"] if r.caps.brightness.value in WRITABLE_LEVELS else 100
                out.append((r, self.app.orch.apply(r.info.id, LightingState(color=Color.parse(color), brightness=bri))))
            return out

        def done(res):
            if isinstance(res, Exception):
                self.toast(str(res), "bad")
                return
            bad = [(r, x) for r, x in res if not x.ok]
            self.toast(f"Applied to {len(res) - len(bad)}/{len(res)}. " + "; ".join(f"{r.info.name}: {x.message}" for r, x in bad)
                       if bad else f"Applied to {len(res)} device(s)", "bad" if bad else "ok")
            self._sig = None
            self.refresh()
        self.bridge.run(work, done)

    def rescan(self):
        self.toast("Scanning…")

        def done(res):
            self.toast(str(res), "bad") if isinstance(res, Exception) else self.toast("Discovery finished", "ok")
            self._sig = None
            self.refresh()
        self.bridge.run(lambda: self.app.rescan(full=True), done)

    def _quit_synapse(self, dev_id):
        rec = self.record(dev_id)
        adapter = self.app.orch.adapters.get(rec.info.adapter) if rec else None
        if not hasattr(adapter, "quit_synapse"):
            return

        def work():
            res = adapter.quit_synapse()
            if res.ok:
                time.sleep(1.0)   # let Synapse's last frame finish before UniRGB asks the mouse again
                self.app.rescan()
            return res

        def done(res):
            ok = not isinstance(res, Exception) and res.ok
            self.toast(str(res) if isinstance(res, Exception) else res.message, "ok" if ok else "bad")
            self._sig = None
            self.refresh()
        self.bridge.run(work, done)
