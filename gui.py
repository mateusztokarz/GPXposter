#!/usr/bin/env python3
"""GPX Poster Designer — interactive Tkinter GUI.

Usage:
    python gui.py [path/to/file.gpx]
"""

from __future__ import annotations

import io
import threading
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
from pathlib import Path
from typing import Optional
import time

from PIL import Image, ImageTk

# ── lazy imports (heavy) ────────────────────────────────────────────────────
_track = None          # parsed TrackData
_gpx_path: Optional[Path] = None
_preview_img: Optional[ImageTk.PhotoImage] = None
_render_job = None     # after() id for debouncing


# ── Constants ────────────────────────────────────────────────────────────────
PREVIEW_W = 380        # preview panel width in px
PREVIEW_H = round(PREVIEW_W * 707 / 500)   # keep B2 aspect ratio
DEBOUNCE_MS = 400      # ms to wait after last slider move before re-rendering


# ─────────────────────────────────────────────────────────────────────────────
# State dict — mirrors all controllable parameters
# ─────────────────────────────────────────────────────────────────────────────
def _default_state() -> dict:
    return dict(
        # text fields
        title        = "Nazwa\nWydarzenia",
        date         = "12.12.2026",
        runner_name  = "Twoje Imię Nazwisko",
        bib          = "0000",
        pace         = "0:00",
        finish_time  = "0:00:00",
        # colours (hex)
        bg_color     = "#4a86b8",
        track_color  = "#d4c84a",
        meta_color   = "#c8dce8",
        # numeric / slider params
        line_width   = 28.0,
        km_every     = 5.0,
        # scale multipliers (1.0 = default size in poster_race.py)
        title_scale  = 1.0,
        date_scale   = 1.0,
        name_scale   = 1.0,
        meta_scale   = 1.0,
        time_scale   = 1.0,
        border_scale = 1.0,
        # Y-offsets (fraction of inner height; 0 = default position)
        title_y_offset = 0.0,
        date_y_offset  = 0.0,
        name_y_offset  = 0.0,
        # X-offsets (fraction of inner width, 0 = default)
        title_x_offset = 0.0,
        date_x_offset  = 0.0,
        name_x_offset  = 0.0,
        meta_x_offset  = 0.0,
        # KM markers
        km_markers_visible = True,
        km_marker_size     = 1.0,
        km_marker_color    = "#000000",
        # Start dot
        start_dot_visible   = True,
        start_dot_size      = 1.0,
        start_dot_color     = "#ffffff",
        start_label_visible = True,
        # Finish dot
        finish_dot_visible   = True,
        finish_dot_size      = 1.0,
        finish_dot_color     = "#ffffff",
        finish_label_visible = True,
        # BIB/Pace gap & scale bar
        meta_gap_scale    = 1.0,
        scale_bar_visible = True,
    )


STATE = _default_state()


# ─────────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _render_preview(state: dict) -> Image.Image:
    """Render a low-res poster and return a PIL Image."""
    if _track is None:
        img = Image.new("RGB", (PREVIEW_W, PREVIEW_H), "#cccccc")
        return img

    from poster_race import generate_race_poster_image

    img = generate_race_poster_image(
        track        = _track,
        event_title  = state["title"],
        event_date   = state["date"],
        runner_name  = state["runner_name"],
        bib          = state["bib"],
        pace         = state["pace"],
        finish_time  = state["finish_time"],
        bg_color     = state["bg_color"],
        track_color  = state["track_color"],
        line_width   = state["line_width"],
        km_every     = state["km_every"],
        title_scale  = state["title_scale"],
        date_scale   = state["date_scale"],
        name_scale   = state["name_scale"],
        meta_scale   = state["meta_scale"],
        time_scale   = state["time_scale"],
        border_scale = state["border_scale"],
        meta_color   = state["meta_color"],
        title_y_offset = state["title_y_offset"],
        date_y_offset  = state["date_y_offset"],
        name_y_offset  = state["name_y_offset"],
        title_x_offset = state["title_x_offset"],
        date_x_offset  = state["date_x_offset"],
        name_x_offset  = state["name_x_offset"],
        meta_x_offset  = state["meta_x_offset"],
        km_markers_visible = state["km_markers_visible"],
        km_marker_size     = state["km_marker_size"],
        km_marker_color    = state["km_marker_color"],
        start_dot_visible  = state["start_dot_visible"],
        start_dot_size     = state["start_dot_size"],
        start_dot_color    = state["start_dot_color"],
        finish_dot_visible = state["finish_dot_visible"],
        finish_dot_size    = state["finish_dot_size"],
        finish_dot_color    = state["finish_dot_color"],
        start_label_visible = state["start_label_visible"],
        finish_label_visible = state["finish_label_visible"],
        meta_gap_scale       = state["meta_gap_scale"],
        scale_bar_visible    = state["scale_bar_visible"],
        preview_size = (PREVIEW_W, PREVIEW_H),
    )
    return img


# ─────────────────────────────────────────────────────────────────────────────
# Main GUI class
# ─────────────────────────────────────────────────────────────────────────────

class PosterDesigner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GPX Poster Designer")
        self.resizable(False, False)
        self._build_ui()
        self._schedule_render()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── top bar ──────────────────────────────────────────────────────────
        top = tk.Frame(self, bg="#222", padx=8, pady=6)
        top.pack(fill="x")

        tk.Button(top, text="📂  Open GPX", command=self._open_gpx,
                  bg="#444", fg="white", relief="flat", padx=10
                  ).pack(side="left", padx=(0, 6))

        self._gpx_label = tk.Label(top, text="No file loaded",
                                   bg="#222", fg="#aaa", anchor="w")
        self._gpx_label.pack(side="left", fill="x", expand=True)

        tk.Button(top, text="💾  Export PDF", command=self._export_pdf,
                  bg="#2a7a2a", fg="white", relief="flat", padx=10
                  ).pack(side="right", padx=(6, 0))
        tk.Button(top, text="🖼  Export PNG", command=self._export_png,
                  bg="#1a5a8a", fg="white", relief="flat", padx=10
                  ).pack(side="right", padx=(6, 0))

        # ── main area: controls (left) + preview (right) ────────────────────
        main = tk.Frame(self)
        main.pack(fill="both", expand=True)

        # Controls panel (scrollable)
        ctrl_outer = tk.Frame(main, width=340, bg="#f0f0f0")
        ctrl_outer.pack(side="left", fill="y")
        ctrl_outer.pack_propagate(False)

        canvas_scroll = tk.Canvas(ctrl_outer, bg="#f0f0f0",
                                  highlightthickness=0, width=330)
        scrollbar = ttk.Scrollbar(ctrl_outer, orient="vertical",
                                  command=canvas_scroll.yview)
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas_scroll.pack(side="left", fill="both", expand=True)

        self._ctrl_frame = tk.Frame(canvas_scroll, bg="#f0f0f0", padx=10)
        self._ctrl_win = canvas_scroll.create_window(
            (0, 0), window=self._ctrl_frame, anchor="nw")

        self._ctrl_frame.bind("<Configure>", lambda e: canvas_scroll.configure(
            scrollregion=canvas_scroll.bbox("all")))
        canvas_scroll.bind("<MouseWheel>", lambda e: canvas_scroll.yview_scroll(
            -1 * (e.delta // 120), "units"))

        # Preview panel
        prev_frame = tk.Frame(main, bg="#888", padx=2, pady=2)
        prev_frame.pack(side="left", fill="both", expand=True)
        self._preview_label = tk.Label(prev_frame, bg="#555",
                                       width=PREVIEW_W, height=PREVIEW_H)
        self._preview_label.pack()

        # Status bar
        self._status = tk.StringVar(value="Ready — open a GPX file to start")
        tk.Label(self, textvariable=self._status, anchor="w",
                 bg="#333", fg="#ccc", padx=8
                 ).pack(fill="x", side="bottom")

        # ── populate controls ────────────────────────────────────────────────
        self._widgets = {}   # name → widget reference
        self._build_controls()

    def _section(self, label: str):
        tk.Label(self._ctrl_frame, text=label, font=("Helvetica", 11, "bold"),
                 bg="#f0f0f0", anchor="w"
                 ).pack(fill="x", pady=(12, 2))
        ttk.Separator(self._ctrl_frame, orient="horizontal").pack(fill="x")

    def _text_field(self, label: str, key: str, height: int = 1):
        tk.Label(self._ctrl_frame, text=label, bg="#f0f0f0",
                 anchor="w", font=("Helvetica", 9)
                 ).pack(fill="x", pady=(6, 1))
        if height == 1:
            var = tk.StringVar(value=STATE[key])
            entry = tk.Entry(self._ctrl_frame, textvariable=var, width=36)
            entry.pack(fill="x")
            var.trace_add("write", lambda *_: self._on_text_change(key, var))
            self._widgets[key] = var
        else:
            text = tk.Text(self._ctrl_frame, height=height, width=36,
                           font=("Helvetica", 10))
            text.insert("1.0", STATE[key])
            text.pack(fill="x")
            text.bind("<KeyRelease>",
                      lambda e, k=key, w=text: self._on_text_area_change(k, w))
            self._widgets[key] = text

    def _slider(self, label: str, key: str,
                from_: float, to: float, resolution: float = 0.1):
        row = tk.Frame(self._ctrl_frame, bg="#f0f0f0")
        row.pack(fill="x", pady=(5, 0))
        tk.Label(row, text=label, bg="#f0f0f0",
                 width=22, anchor="w", font=("Helvetica", 9)
                 ).pack(side="left")
        val_label = tk.Label(row, text=f"{STATE[key]:.1f}",
                             bg="#f0f0f0", width=5, font=("Helvetica", 9))
        val_label.pack(side="right")
        var = tk.DoubleVar(value=STATE[key])
        slider = ttk.Scale(self._ctrl_frame, from_=from_, to=to,
                           variable=var, orient="horizontal")
        slider.pack(fill="x")

        def on_change(*_):
            v = round(var.get() / resolution) * resolution
            STATE[key] = v
            val_label.config(text=f"{v:.1f}")
            self._schedule_render()

        var.trace_add("write", on_change)
        self._widgets[key] = var

    def _color_button(self, label: str, key: str):
        row = tk.Frame(self._ctrl_frame, bg="#f0f0f0")
        row.pack(fill="x", pady=(5, 0))
        tk.Label(row, text=label, bg="#f0f0f0",
                 anchor="w", font=("Helvetica", 9), width=22
                 ).pack(side="left")
        swatch = tk.Label(row, bg=STATE[key], width=4, relief="groove")
        swatch.pack(side="right", padx=4)
        hex_var = tk.StringVar(value=STATE[key])
        hex_entry = tk.Entry(row, textvariable=hex_var, width=9,
                             font=("Courier", 9))
        hex_entry.pack(side="right")

        def pick():
            c = colorchooser.askcolor(color=STATE[key],
                                      title=f"Choose {label}")[1]
            if c:
                STATE[key] = c
                hex_var.set(c)
                swatch.config(bg=c)
                self._schedule_render()

        def on_hex(*_):
            v = hex_var.get().strip()
            if len(v) == 7 and v.startswith("#"):
                try:
                    self.winfo_rgb(v)   # validate
                    STATE[key] = v
                    swatch.config(bg=v)
                    self._schedule_render()
                except Exception:
                    pass

        tk.Button(row, text="🎨", command=pick,
                  relief="flat", bg="#f0f0f0"
                  ).pack(side="right")
        hex_var.trace_add("write", on_hex)

    def _checkbox(self, label: str, key: str):
        """Boolean toggle checkbox."""
        var = tk.BooleanVar(value=STATE[key])
        cb = tk.Checkbutton(self._ctrl_frame, text=label, variable=var,
                            bg="#f0f0f0", anchor="w",
                            font=("Helvetica", 9))
        cb.pack(fill="x", pady=(4, 0))

        def on_change(*_):
            STATE[key] = var.get()
            self._schedule_render()

        var.trace_add("write", on_change)
        self._widgets[key] = var

    def _build_controls(self):
        f = self._ctrl_frame

        self._section("📄 Text Content")
        self._text_field("Event title  (use \\n for new line)", "title", height=2)
        self._text_field("Date", "date")
        self._text_field("Runner name", "runner_name")
        self._text_field("BIB number", "bib")
        self._text_field("Pace (e.g. 5:12)", "pace")
        self._text_field("Finish time (e.g. 1:49:33)", "finish_time")

        self._section("🎨 Colours")
        self._color_button("Background colour",  "bg_color")
        self._color_button("Track colour",       "track_color")
        self._color_button("BIB / Pace colour",  "meta_color")

        self._section("📏 Track")
        self._slider("Track line width (px)", "line_width", 5, 80, 1)

        self._section("📍 KM Markers")
        self._checkbox("Show KM markers", "km_markers_visible")
        self._slider("KM marker every (km)",  "km_every",       1,   10,  0.5)
        self._slider("KM marker size (×)",    "km_marker_size", 0.2, 3.0, 0.1)
        self._color_button("KM marker colour", "km_marker_color")

        self._section("🏁 Start & Finish Dots")
        self._checkbox("Show Start dot",          "start_dot_visible")
        self._slider("Start dot size (×)",        "start_dot_size",  0.2, 4.0, 0.1)
        self._color_button("Start dot colour",    "start_dot_color")
        self._checkbox('Show "Start" label',      "start_label_visible")
        self._checkbox("Show Finish dot",         "finish_dot_visible")
        self._slider("Finish dot size (×)",       "finish_dot_size", 0.2, 4.0, 0.1)
        self._color_button("Finish dot colour",   "finish_dot_color")
        self._checkbox('Show "Finish" label',     "finish_label_visible")

        self._section("🔤 Font Sizes  (×  default)")
        self._slider("Title size",       "title_scale",  0.4, 2.0, 0.05)
        self._slider("Date size",        "date_scale",   0.4, 2.0, 0.05)
        self._slider("Name size",        "name_scale",   0.4, 2.0, 0.05)
        self._slider("BIB / Pace size",  "meta_scale",    0.4, 2.0, 0.05)
        self._slider("BIB / Pace gap (×)", "meta_gap_scale", 0.0, 8.0, 0.1)
        self._slider("Finish time size", "time_scale",   0.4, 2.0, 0.05)

        self._section("↕ Text Y-Position  (↑ negative  /  ↓ positive)")
        self._slider("Title vertical offset",  "title_y_offset", -0.15, 0.15, 0.005)
        self._slider("Date vertical offset",   "date_y_offset",  -0.15, 0.15, 0.005)
        self._slider("Name vertical offset",   "name_y_offset",  -0.15, 0.15, 0.005)

        self._section("↔ Text X-Position  (← negative  /  → positive)")
        self._slider("Title horizontal offset",   "title_x_offset", -0.5, 0.5, 0.005)
        self._slider("Date horizontal offset",    "date_x_offset",  -0.5, 0.5, 0.005)
        self._slider("Name horizontal offset",    "name_x_offset",  -0.5, 0.5, 0.005)
        self._slider("BIB/Pace horizontal offset","meta_x_offset",  -0.5, 0.5, 0.005)

        self._section("🖼 Layout")
        self._slider("White border width", "border_scale", 0.0, 3.0, 0.1)
        self._checkbox("Show km scale bar", "scale_bar_visible")

        # Reset button
        tk.Button(f, text="↺  Reset all to defaults",
                  command=self._reset_all,
                  bg="#e0e0e0", relief="flat", padx=6, pady=4
                  ).pack(fill="x", pady=(16, 4))

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_text_change(self, key: str, var: tk.StringVar):
        STATE[key] = var.get()
        self._schedule_render()

    def _on_text_area_change(self, key: str, widget: tk.Text):
        STATE[key] = widget.get("1.0", "end-1c")
        self._schedule_render()

    def _schedule_render(self):
        global _render_job
        if _render_job is not None:
            self.after_cancel(_render_job)
        _render_job = self.after(DEBOUNCE_MS, self._do_render)

    def _do_render(self):
        global _render_job
        _render_job = None
        if _track is None:
            return
        self._status.set("Rendering preview…")
        self.update_idletasks()
        t0 = time.time()
        try:
            img = _render_preview(dict(STATE))
            photo = ImageTk.PhotoImage(img)
            self._preview_label.configure(image=photo)
            self._preview_label.image = photo   # keep reference
            elapsed = time.time() - t0
            self._status.set(f"Preview updated in {elapsed:.1f}s — "
                             f"{_gpx_path.name if _gpx_path else ''}")
        except Exception as exc:
            self._status.set(f"Render error: {exc}")

    def _open_gpx(self):
        global _track, _gpx_path
        path = filedialog.askopenfilename(
            title="Open GPX file",
            filetypes=[("GPX files", "*.gpx"), ("All files", "*.*")],
        )
        if not path:
            return
        _gpx_path = Path(path)
        self._status.set(f"Loading {_gpx_path.name}…")
        self.update_idletasks()
        try:
            from gpx_parser import parse_gpx
            _track = parse_gpx(_gpx_path)
            s = _track.stats
            self._gpx_label.config(
                text=f"{_gpx_path.name}  ·  {s.distance_km:.1f} km  "
                     f"·  +{s.elevation_gain_m:.0f} m  "
                     f"·  {len(_track.lats):,} pts",
                fg="white",
            )
            self._schedule_render()
        except Exception as exc:
            messagebox.showerror("Error loading GPX", str(exc))

    def _export_pdf(self):
        self._export("pdf")

    def _export_png(self):
        self._export("png")

    def _export(self, fmt: str):
        if _track is None:
            messagebox.showwarning("No file", "Please open a GPX file first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(f"{fmt.upper()} files", f"*.{fmt}"),
                       ("All files", "*.*")],
            initialfile=f"poster.{fmt}",
        )
        if not path:
            return
        self._status.set(f"Exporting {fmt.upper()}…")
        self.update_idletasks()
        try:
            from poster_race import generate_race_poster
            generate_race_poster(
                track        = _track,
                output_path  = path,
                event_title  = STATE["title"],
                event_date   = STATE["date"],
                runner_name  = STATE["runner_name"],
                bib          = STATE["bib"],
                pace         = STATE["pace"],
                finish_time  = STATE["finish_time"],
                bg_color     = STATE["bg_color"],
                track_color  = STATE["track_color"],
                line_width   = STATE["line_width"],
                km_every     = STATE["km_every"],
                title_scale  = STATE["title_scale"],
                date_scale   = STATE["date_scale"],
                name_scale   = STATE["name_scale"],
                meta_scale   = STATE["meta_scale"],
                time_scale   = STATE["time_scale"],
                border_scale = STATE["border_scale"],
                meta_color   = STATE["meta_color"],
                title_y_offset = STATE["title_y_offset"],
                date_y_offset  = STATE["date_y_offset"],
                name_y_offset  = STATE["name_y_offset"],
                title_x_offset = STATE["title_x_offset"],
                date_x_offset  = STATE["date_x_offset"],
                name_x_offset  = STATE["name_x_offset"],
                meta_x_offset  = STATE["meta_x_offset"],
                km_markers_visible = STATE["km_markers_visible"],
                km_marker_size     = STATE["km_marker_size"],
                km_marker_color    = STATE["km_marker_color"],
                start_dot_visible  = STATE["start_dot_visible"],
                start_dot_size     = STATE["start_dot_size"],
                start_dot_color    = STATE["start_dot_color"],
                finish_dot_visible = STATE["finish_dot_visible"],
                finish_dot_size    = STATE["finish_dot_size"],
                finish_dot_color    = STATE["finish_dot_color"],
                start_label_visible  = STATE["start_label_visible"],
                finish_label_visible = STATE["finish_label_visible"],
                meta_gap_scale       = STATE["meta_gap_scale"],
                scale_bar_visible    = STATE["scale_bar_visible"],
            )
            self._status.set(f"Saved → {path}")
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))

    def _reset_all(self):
        global STATE
        defaults = _default_state()
        STATE.update(defaults)
        # Update all widget values
        for key, widget in self._widgets.items():
            if isinstance(widget, tk.StringVar):
                widget.set(defaults[key])
            elif isinstance(widget, tk.DoubleVar):
                widget.set(defaults[key])
            elif isinstance(widget, tk.Text):
                widget.delete("1.0", "end")
                widget.insert("1.0", defaults[key])
        self._schedule_render()


# ─────────────────────────────────────────────────────────────────────────────
# Patch poster_race to expose a generate_race_poster_image() function
# ─────────────────────────────────────────────────────────────────────────────

def _patch_poster_race():
    """No-op kept for compatibility — generate_race_poster_image is now in poster_race."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Patch poster_race to expose the canvas renderer
    _patch_poster_race()

    app = PosterDesigner()

    # Auto-load GPX if passed as argument
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            _gpx_path = p
            from gpx_parser import parse_gpx
            _track = parse_gpx(p)
            s = _track.stats
            app._gpx_label.config(
                text=f"{p.name}  ·  {s.distance_km:.1f} km  "
                     f"·  +{s.elevation_gain_m:.0f} m  "
                     f"·  {len(_track.lats):,} pts",
                fg="white",
            )
            app._schedule_render()

    app.mainloop()
