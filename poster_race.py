"""Race-style poster compositor — matches the reference design.

Layout proportions (B2 = 500×707 mm @ 300 DPI = 5906×8346 px):

  ┌─────────────────────────────────┐  ← y=0
  │                                 │
  │  Półmaraton          27.09.26   │  ← HUGE title (~25% of height)
  │  Gdańsk                         │
  │                                 │
  │    ┌───────────────────────┐    │
  │    │   [route map]         │    │  ← map ~38% of height, centred
  │    │   km markers          │    │
  │    └───────────────────────┘    │
  │                                 │
  │  Twoje                          │
  │  Imię Nazwisko                  │  ← large name ~12%
  │  BIB 0000   Pace 0:00           │
  ├~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~┤  ← elevation profile = torn edge (~5%)
  │                                 │  ← white zone ~20%
  │        0:00:00                  │  ← HUGE time
  │  0  2  4  6 … km               │  ← scale bar
  └─────────────────────────────────┘
"""

from __future__ import annotations

import io
import math
import numpy as np
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

from gpx_parser import TrackData
from map_renderer import _equal_aspect_padding, map_aspect_ratio


# ---------------------------------------------------------------------------
# Canvas constants
# ---------------------------------------------------------------------------
B2_W_MM, B2_H_MM = 500, 707
POSTER_DPI = 300
PW = round(B2_W_MM / 25.4 * POSTER_DPI)   # 5906
PH = round(B2_H_MM / 25.4 * POSTER_DPI)   # 8346

# Default colours
BLUE_BG   = "#4a86b8"
TRACK_COL = "#d4c84a"

# Font paths
# Regular and bold font paths searched in order (macOS + Linux/Ubuntu)
_FONT_PATHS_REGULAR = [
    # Linux — Liberation Sans (installed via packages.txt)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # Linux — DejaVu fallback (always present on Ubuntu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]

_FONT_PATHS_BOLD = [
    # Linux — Liberation Sans Bold
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Linux — DejaVu fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    # macOS (.ttc index 1 = bold)
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REGULAR
    for path in paths:
        try:
            # .ttc files: index 1 = bold variant on macOS
            idx = 1 if (bold and path.endswith(".ttc")) else 0
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            pass
    return ImageFont.load_default()


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _th(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


# ---------------------------------------------------------------------------
# Elevation profile → torn edge
# ---------------------------------------------------------------------------

def _torn_edge(canvas: Image.Image, track: TrackData,
               top_y: int, strip_h: int, bg_color: str):
    """Paint the torn-edge elevation profile strip.

    Above the profile line → blue (already painted).
    Below the profile line → white down to canvas bottom.
    """
    from scipy.ndimage import gaussian_filter1d

    elevs = np.array([e for e in track.elevations if e is not None], dtype=float)
    if len(elevs) < 2:
        elevs = np.zeros(2)

    # Resample to canvas width
    xs = np.linspace(0, 1, PW)
    ys = np.interp(xs, np.linspace(0, 1, len(elevs)), elevs)
    ys = gaussian_filter1d(ys, sigma=max(1, PW / 600))

    # Normalise: high elevation → small offset from top_y (peaks upward)
    y_min, y_max = ys.min(), ys.max()
    if y_max > y_min:
        ys_n = (ys - y_min) / (y_max - y_min)
    else:
        ys_n = np.full_like(ys, 0.5)

    abs_y = (top_y + (1.0 - ys_n) * strip_h).astype(int)

    draw = ImageDraw.Draw(canvas)
    for x in range(PW):
        y = int(abs_y[x])
        # white from profile line to canvas bottom
        if y < PH:
            draw.line([(x, y), (x, PH)], fill=(255, 255, 255))

    return int(abs_y.min())   # topmost point of profile (highest peak)


# ---------------------------------------------------------------------------
# KM markers
# ---------------------------------------------------------------------------

def _km_positions(track: TrackData, every_km: float = 5.0):
    from gpx_parser import _haversine_km
    markers, dist, nxt = [], 0.0, every_km
    for i in range(1, len(track.lats)):
        dist += _haversine_km(track.lats[i-1], track.lons[i-1],
                              track.lats[i],   track.lons[i])
        if dist >= nxt:
            markers.append((track.lats[i], track.lons[i], int(round(nxt))))
            nxt += every_km
    return markers


# ---------------------------------------------------------------------------
# Map render
# ---------------------------------------------------------------------------

def _render_map(track: TrackData, bg: str, color: str,
                w_px: int, h_px: int, dpi: int,
                line_width: float, km_every: float,
                km_markers_visible: bool = True,
                km_marker_size: float = 1.0,
                km_marker_color: str = "#000000",
                start_dot_visible: bool = True,
                start_dot_size: float = 1.0,
                start_dot_color: str = "#ffffff",
                finish_dot_visible: bool = True,
                finish_dot_size: float = 1.0,
                finish_dot_color: str = "#ffffff",
                start_label_visible: bool = True,
                finish_label_visible: bool = True,
                ) -> Image.Image:
    """Render the route map as a PIL Image of exactly (w_px × h_px).

    Draws directly in pixel space using PIL so line width is always exactly
    `line_width` pixels — no matplotlib point/unit confusion.
    """
    from PIL import ImageDraw as ID

    lat_min, lat_max, lon_min, lon_max = _equal_aspect_padding(
        *track.bounds, pad_frac=0.04)

    bg_rgb = tuple(int(bg.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    track_rgb = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    img  = Image.new("RGB", (w_px, h_px), bg_rgb)
    draw = ID.Draw(img)

    def to_px(lat, lon):
        """Map lat/lon to pixel coordinates."""
        x = round((lon - lon_min) / (lon_max - lon_min) * w_px)
        y = round((1 - (lat - lat_min) / (lat_max - lat_min)) * h_px)
        return (x, y)

    # Draw track line using PIL line (exact pixel width)
    lw = max(1, round(line_width))
    pts = [to_px(lat, lon) for lat, lon in zip(track.lats, track.lons)]
    # Draw as polyline in chunks to avoid performance issues
    chunk = 500
    for i in range(0, len(pts) - 1, chunk - 1):
        segment = pts[i:i + chunk]
        if len(segment) >= 2:
            draw.line(segment, fill=track_rgb, width=lw, joint="curve")

    # KM markers — coloured circle with white number
    base_marker_r  = max(18, round(w_px * 0.022))
    marker_r       = max(4,  round(base_marker_r * km_marker_size))
    font_size      = max(10, round(marker_r * 1.1))
    label_font_size = max(8, round(base_marker_r * 0.7))
    km_font  = _font(font_size,        bold=True)
    lbl_font = _font(label_font_size,  bold=False)

    km_marker_rgb = _hex_rgb(km_marker_color)

    if km_markers_visible:
        for lat, lon, km in _km_positions(track, km_every):
            cx, cy = to_px(lat, lon)
            draw.ellipse([cx - marker_r, cy - marker_r,
                          cx + marker_r, cy + marker_r],
                         fill=km_marker_rgb)
            text = str(km)
            bb = draw.textbbox((0, 0), text, font=km_font)
            tw, th = bb[2]-bb[0], bb[3]-bb[1]
            draw.text((cx - tw//2, cy - th//2), text,
                      font=km_font, fill=(255, 255, 255))

    # Start / Finish labels
    sx, sy = to_px(track.lats[0],  track.lons[0])
    fx, fy = to_px(track.lats[-1], track.lons[-1])
    off = round(w_px * 0.018)

    # Start dot
    base_dot_r = max(14, round(w_px * 0.016))
    if start_dot_visible:
        sr = max(4, round(base_dot_r * start_dot_size))
        s_rgb = _hex_rgb(start_dot_color)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=s_rgb)
    if start_label_visible:
        draw.text((sx + off, sy + off), "Start",
                  font=lbl_font, fill=(255, 255, 255))

    # Finish dot
    if finish_dot_visible:
        fr = max(4, round(base_dot_r * finish_dot_size))
        f_rgb = _hex_rgb(finish_dot_color)
        draw.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=f_rgb)
    if finish_label_visible:
        draw.text((fx + off, fy - off - label_font_size), "Finish",
                  font=lbl_font, fill=(255, 255, 255))

    return img


# ---------------------------------------------------------------------------
# Scale bar
# ---------------------------------------------------------------------------

def _scale_bar(draw, total_km, x, y, width, font, color):
    raw = total_km / 10
    step = next((s for s in [0.5,1,2,2.5,5,10,20] if s >= raw), round(raw))
    ticks = np.arange(0, total_km + step*0.5, step)
    pxkm = width / total_km
    bh = max(2, round(0.018 * POSTER_DPI))
    th = round(0.03  * POSTER_DPI)
    ldy= round(0.025 * POSTER_DPI)

    draw.rectangle([x, y, x+width, y+bh], fill=(*color[:3], 80))
    for km in ticks:
        tx = round(x + km * pxkm)
        draw.line([(tx, y-th), (tx, y+bh+th)], fill=color,
                  width=max(1, round(0.006*POSTER_DPI)))
        lbl = f"{km:.0f}" if km == int(km) else f"{km}"
        lw = draw.textbbox((0,0), lbl, font=font)[2]
        draw.text((tx - lw//2, y+bh+ldy), lbl, font=font, fill=color)
    end_x = round(x + total_km * pxkm + round(0.03*POSTER_DPI))
    draw.text((end_x, y+bh+ldy), "km", font=font, fill=color)


# ---------------------------------------------------------------------------
# Core renderer — returns PIL Image (used by both CLI and GUI)
# ---------------------------------------------------------------------------

def _render_poster_canvas(
    track: TrackData,
    event_title: str = "",
    event_date:  str = "",
    runner_name: str = "",
    bib:         str = "",
    pace:        str = "",
    finish_time: str = "0:00:00",
    bg_color:    str = BLUE_BG,
    track_color: str = TRACK_COL,
    line_width:  float = 28.0,
    km_every:    float = 5.0,
    # Scale multipliers (1.0 = default)
    title_scale:  float = 1.0,
    date_scale:   float = 1.0,
    name_scale:   float = 1.0,
    meta_scale:   float = 1.0,
    time_scale:   float = 1.0,
    border_scale: float = 1.0,
    # Y-offsets for text elements (fraction of inner height, default 0 = centred/default)
    title_y_offset: float = 0.0,
    date_y_offset:  float = 0.0,
    name_y_offset:  float = 0.0,
    # KM markers
    km_markers_visible: bool  = True,
    km_marker_size:     float = 1.0,
    km_marker_color:    str   = "#000000",
    # Start / Finish dots
    start_dot_visible: bool  = True,
    start_dot_size:    float = 1.0,
    start_dot_color:   str   = "#ffffff",
    finish_dot_visible: bool  = True,
    finish_dot_size:    float = 1.0,
    finish_dot_color:   str   = "#ffffff",
    start_label_visible:  bool = True,
    finish_label_visible: bool = True,
    # BIB / Pace text colour
    meta_color: str = "#c8dce8",
) -> Image.Image:
    """Render the full B2 poster and return a PIL Image."""
    bg_rgb = _hex_rgb(bg_color)

    BORDER = round(0.28 * POSTER_DPI * border_scale)
    IW = PW - 2 * BORDER
    IH = PH - 2 * BORDER

    canvas_outer = Image.new("RGB", (PW, PH), (255, 255, 255))
    canvas = Image.new("RGB", (IW, IH), bg_rgb)

    M = round(0.38 * POSTER_DPI)

    title_zone_h = round(IH * 0.235)
    profile_h    = round(IH * 0.050)
    name_zone_h  = round(IH * 0.115)
    min_white_h  = round(IH * 0.175)
    map_zone_h   = IH - title_zone_h - name_zone_h - profile_h - min_white_h
    white_zone_h = IH - title_zone_h - map_zone_h - name_zone_h - profile_h

    title_y   = 0
    map_y     = title_zone_h
    name_y    = map_y + map_zone_h
    profile_y = name_y + name_zone_h
    white_y   = profile_y + profile_h
    content_w = IW - 2 * M

    # Y-offset in pixels (offset multiplied by IH for convenient slider range)
    _title_y_off = round(title_y_offset * IH)
    _date_y_off  = round(date_y_offset  * IH)
    _name_y_off  = round(name_y_offset  * IH)

    # Font sizes — base × scale multiplier
    title_size = round(title_zone_h * 0.38 * title_scale)
    date_size  = round(title_zone_h * 0.18 * date_scale)
    name_size  = round(name_zone_h  * 0.38 * name_scale)
    meta_size  = round(name_zone_h  * 0.22 * meta_scale)
    time_size  = round(white_zone_h * 0.58 * time_scale)
    scale_size = round(POSTER_DPI   * 0.13)

    # 1. Map
    map_img = _render_map(
        track, bg_color, track_color,
        IW, map_zone_h, POSTER_DPI, line_width, km_every,
        km_markers_visible=km_markers_visible,
        km_marker_size=km_marker_size,
        km_marker_color=km_marker_color,
        start_dot_visible=start_dot_visible,
        start_dot_size=start_dot_size,
        start_dot_color=start_dot_color,
        finish_dot_visible=finish_dot_visible,
        finish_dot_size=finish_dot_size,
        finish_dot_color=finish_dot_color,
        start_label_visible=start_label_visible,
        finish_label_visible=finish_label_visible,
    )
    canvas.paste(map_img, (0, map_y))

    # 2. Elevation profile torn edge
    _torn_edge(canvas, track, profile_y, profile_h, bg_color)

    # 3. Text
    draw  = ImageDraw.Draw(canvas)
    WHITE = (255, 255, 255)
    BLACK = (10, 10, 10)
    MUTED = _hex_rgb(meta_color)

    f_title = _font(title_size, bold=True)
    f_date  = _font(date_size,  bold=False)
    f_name  = _font(name_size,  bold=True)
    f_meta  = _font(meta_size,  bold=False)
    f_time  = _font(time_size,  bold=True)
    f_scale = _font(scale_size, bold=False)

    # Title
    title_lines  = (event_title or track.stats.name).replace("\\n", "\n").split("\n")
    line_heights = [_th(draw, ln, f_title) for ln in title_lines]
    line_gap     = round(title_size * 0.04)
    block_h      = sum(line_heights) + line_gap * (len(line_heights) - 1)
    ty = title_y + (title_zone_h - block_h) // 2 + _title_y_off
    for i, line in enumerate(title_lines):
        draw.text((M, ty), line, font=f_title, fill=WHITE)
        ty += line_heights[i] + line_gap

    # Date
    if event_date:
        dw = _tw(draw, event_date, f_date)
        dh = _th(draw, event_date, f_date)
        draw.text((IW - M - dw,
                   title_y + (title_zone_h - dh) // 2 + _date_y_off),
                  event_date, font=f_date, fill=WHITE)

    # Runner name (two lines)
    name_text = runner_name or ""
    if name_text:
        words = name_text.split()
        if len(words) >= 2:
            mid = max(1, len(words) // 2)
            name_lines = [" ".join(words[:mid]), " ".join(words[mid:])]
        else:
            name_lines = [name_text]
        name_line_h = [_th(draw, ln, f_name) for ln in name_lines]
        name_gap    = round(name_size * 0.06)
        ny = name_y + round(POSTER_DPI * 0.05) + _name_y_off
        for i, ln in enumerate(name_lines):
            draw.text((M, ny), ln, font=f_name, fill=WHITE)
            ny += name_line_h[i] + name_gap
        meta_parts = []
        if bib:  meta_parts.append(f"BIB {bib}")
        if pace: meta_parts.append(f"Pace {pace}")
        if meta_parts:
            draw.text((M, ny + round(POSTER_DPI * 0.02)),
                      "   ".join(meta_parts), font=f_meta, fill=MUTED)

    # Finish time
    tw_px     = _tw(draw, finish_time, f_time)
    time_y_px = white_y + round((white_zone_h - time_size) * 0.25)
    draw.text(((IW - tw_px) // 2, time_y_px), finish_time, font=f_time, fill=BLACK)

    # Scale bar
    scale_y_px = time_y_px + time_size + round(POSTER_DPI * 0.07)
    _scale_bar(draw, track.stats.distance_km, M, scale_y_px, content_w, f_scale, BLACK)

    # 4. Composite
    canvas_outer.paste(canvas, (BORDER, BORDER))
    return canvas_outer


# ---------------------------------------------------------------------------
# Public API — file-saving wrapper used by CLI
# ---------------------------------------------------------------------------

def generate_race_poster(
    track: TrackData,
    output_path: str | Path = "poster_race.pdf",
    event_title: str = "",
    event_date:  str = "",
    runner_name: str = "",
    bib:         str = "",
    pace:        str = "",
    finish_time: str = "0:00:00",
    km_every:    float = 5.0,
    bg_color:    str = BLUE_BG,
    track_color: str = TRACK_COL,
    line_width:  float = 28.0,
    title_scale:  float = 1.0,
    date_scale:   float = 1.0,
    name_scale:   float = 1.0,
    meta_scale:   float = 1.0,
    time_scale:   float = 1.0,
    border_scale: float = 1.0,
    title_y_offset: float = 0.0,
    date_y_offset:  float = 0.0,
    name_y_offset:  float = 0.0,
    km_markers_visible: bool  = True,
    km_marker_size:     float = 1.0,
    km_marker_color:    str   = "#000000",
    start_dot_visible: bool  = True,
    start_dot_size:    float = 1.0,
    start_dot_color:   str   = "#ffffff",
    finish_dot_visible: bool  = True,
    finish_dot_size:    float = 1.0,
    finish_dot_color:   str   = "#ffffff",
    start_label_visible:  bool = True,
    finish_label_visible: bool = True,
    meta_color:           str  = "#c8dce8",
) -> Path:
    output_path = Path(output_path)
    img = _render_poster_canvas(
        track=track, event_title=event_title, event_date=event_date,
        runner_name=runner_name, bib=bib, pace=pace, finish_time=finish_time,
        bg_color=bg_color, track_color=track_color,
        line_width=line_width, km_every=km_every,
        title_scale=title_scale, date_scale=date_scale,
        name_scale=name_scale, meta_scale=meta_scale,
        time_scale=time_scale, border_scale=border_scale,
        title_y_offset=title_y_offset, date_y_offset=date_y_offset,
        name_y_offset=name_y_offset,
        km_markers_visible=km_markers_visible,
        km_marker_size=km_marker_size, km_marker_color=km_marker_color,
        start_dot_visible=start_dot_visible,
        start_dot_size=start_dot_size, start_dot_color=start_dot_color,
        finish_dot_visible=finish_dot_visible,
        finish_dot_size=finish_dot_size, finish_dot_color=finish_dot_color,
        start_label_visible=start_label_visible,
        finish_label_visible=finish_label_visible,
        meta_color=meta_color,
    )
    suffix = output_path.suffix.lower()
    if suffix == ".pdf":
        _save_pdf(img, output_path)
    else:
        img.save(str(output_path), dpi=(POSTER_DPI, POSTER_DPI))

    preview = output_path.with_suffix(".png")
    img.resize((PW//3, PH//3), Image.LANCZOS).save(str(preview), dpi=(100, 100))
    return output_path


def generate_race_poster_image(
    track: TrackData,
    preview_size: tuple = None,
    **kwargs,
) -> Image.Image:
    """Return PIL Image — used by GUI for live preview."""
    img = _render_poster_canvas(track=track, **kwargs)
    if preview_size:
        img = img.resize(preview_size, Image.LANCZOS)
    return img


def _save_pdf(canvas: Image.Image, path: Path):
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    PAGE_W, PAGE_H = B2_W_MM * mm, B2_H_MM * mm
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", dpi=(POSTER_DPI, POSTER_DPI))
    buf.seek(0)
    c = rl_canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.drawInlineImage(Image.open(buf), 0, 0, width=PAGE_W, height=PAGE_H)
    c.save()
