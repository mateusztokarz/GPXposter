"""Poster compositor — assembles map, elevation profile and stats into a
print-ready B2 (500×707 mm) layout and saves as PDF + PNG.

B2 at 300 DPI  →  5906 × 8346 pixels
                   19.69 × 27.76 inches
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import numpy as np
from PIL import Image

from gpx_parser import TrackData, TrackStats
from map_renderer import THEMES, render_map, render_elevation_profile


# B2 dimensions in inches at 300 DPI
B2_W_IN = 500 / 25.4   # 19.685 in
B2_H_IN = 707 / 25.4   # 27.835 in
POSTER_DPI = 300


def _fmt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def _fig_to_pil(fig: plt.Figure) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=POSTER_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return Image.open(buf).copy()


def _paste_fig(canvas: Image.Image, fig: plt.Figure,
               x: int, y: int, w: int, h: int) -> None:
    img = _fig_to_pil(fig)
    img = img.resize((w, h), Image.LANCZOS)
    canvas.paste(img, (x, y))


def generate_poster(
    track: TrackData,
    output_path: str | Path = "poster.pdf",
    theme: str = "dark",
    subtitle: str = "",
    show_elevation: bool = True,
    color_by: str = "progress",
) -> Path:
    """Generate and save the B2 poster. Returns the Path of saved file."""
    from map_renderer import map_aspect_ratio
    output_path = Path(output_path)
    pal = THEMES.get(theme, THEMES["dark"])

    # Canvas size in pixels
    PW = round(B2_W_IN * POSTER_DPI)   # 5906
    PH = round(B2_H_IN * POSTER_DPI)   # 8346

    canvas = Image.new("RGB", (PW, PH), pal["bg"])

    # ---- Layout constants (all in pixels) ---------------------------------- #
    MARGIN    = round(0.38 * POSTER_DPI)
    content_x = MARGIN
    content_w = PW - 2 * MARGIN

    # --- Fixed zones -------------------------------------------------------- #
    header_h = round(1.3 * POSTER_DPI)
    elev_h   = round(1.6 * POSTER_DPI) if show_elevation else 0
    stats_h  = round(1.4 * POSTER_DPI)
    footer_h = round(0.35 * POSTER_DPI)
    gap      = round(0.14 * POSTER_DPI)

    # --- Map: height derived from true projected aspect ratio --------------- #
    # map_aspect_ratio returns lon_km / lat_km = width/height
    ar    = map_aspect_ratio(track)
    map_w = content_w
    map_h = round(map_w / ar)

    # Total vertical budget — stack tightly, no wasted space at bottom
    non_map  = header_h + elev_h + stats_h + footer_h + 4 * gap + 2 * MARGIN
    max_map_h = PH - non_map

    # If natural height overflows, scale down proportionally
    if map_h > max_map_h:
        map_h = max_map_h
        map_w = round(map_h * ar)

    map_x = content_x + (content_w - map_w) // 2

    # Stack all zones top → bottom (tight, no leftover black gap)
    header_top = MARGIN
    map_top    = header_top + header_h + gap
    elev_top   = map_top + map_h + gap
    stats_top  = elev_top + (elev_h if show_elevation else 0) + gap
    footer_top = stats_top + stats_h + gap

    # ---- Render map -------------------------------------------------------- #
    map_fig = render_map(
        track, theme=theme, dpi=POSTER_DPI,
        fig_width_in=map_w / POSTER_DPI,
        fig_height_in=map_h / POSTER_DPI,
        line_width=2.4, color_by=color_by,
    )
    _paste_fig(canvas, map_fig, map_x, map_top, map_w, map_h)

    # ---- Render elevation profile ------------------------------------------ #
    if show_elevation:
        elev_fig = render_elevation_profile(
            track, theme=theme, dpi=POSTER_DPI,
            fig_width_in=content_w / POSTER_DPI,
            fig_height_in=elev_h / POSTER_DPI,
        )
        if elev_fig:
            _paste_fig(canvas, elev_fig, content_x, elev_top, content_w, elev_h)

    # ---- Stats bar --------------------------------------------------------- #
    _draw_stats_on_canvas(canvas, track.stats, pal,
                          content_x, stats_top, content_w, stats_h, POSTER_DPI)

    # ---- Header ------------------------------------------------------------ #
    _draw_header_on_canvas(canvas, track.stats.name, subtitle, pal,
                           content_x, header_top, content_w, header_h, POSTER_DPI)

    # ---- Footer ------------------------------------------------------------ #
    _draw_footer_on_canvas(canvas, pal, content_x, footer_top, content_w,
                           footer_h, POSTER_DPI)

    # ---- Save -------------------------------------------------------------- #
    suffix = output_path.suffix.lower()

    if suffix == ".pdf":
        # Save PDF via Matplotlib for proper vector title + raster map
        _save_pdf(canvas, output_path, PW, PH)
    else:
        canvas.save(str(output_path), dpi=(POSTER_DPI, POSTER_DPI))

    # Always also save a PNG preview (approx 1/3 size)
    preview_path = output_path.with_suffix(".png")
    preview = canvas.resize(
        (round(PW / 3), round(PH / 3)), Image.LANCZOS
    )
    preview.save(str(preview_path), dpi=(100, 100))

    return output_path


# --------------------------------------------------------------------------- #
# Drawing helpers using PIL ImageDraw                                          #
# --------------------------------------------------------------------------- #

def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _draw_header_on_canvas(canvas, title, subtitle, pal,
                            x, y, w, h, dpi):
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(canvas)
    cx = x + w // 2

    # Title
    title_size = round(dpi * 0.55)
    try:
        from PIL import ImageFont
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                        title_size)
    except Exception:
        font_title = ImageFont.load_default()

    sub_size = round(dpi * 0.22)
    try:
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                      sub_size)
    except Exception:
        font_sub = ImageFont.load_default()

    is_dark = pal["bg"] in ("#0d0d0d", "#0a1628", "#0f1a0f")
    text_color = (255, 255, 255) if is_dark else (30, 30, 30)
    muted_color = (150, 150, 150) if is_dark else (100, 100, 100)

    # Thin decorative line
    line_y = y + round(dpi * 0.08)
    accent = _hex_to_rgb(pal["track_cmap"][0])
    draw.rectangle([x, line_y, x + w, line_y + round(dpi * 0.025)],
                   fill=accent)

    # Title text centred
    title_y = y + round(dpi * 0.15)
    bbox = draw.textbbox((0, 0), title.upper(), font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw // 2, title_y), title.upper(),
              font=font_title, fill=text_color)

    # Subtitle
    if subtitle:
        sub_y = title_y + title_size + round(dpi * 0.06)
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw = bbox2[2] - bbox2[0]
        draw.text((cx - sw // 2, sub_y), subtitle,
                  font=font_sub, fill=muted_color)


def _draw_stats_on_canvas(canvas, stats: TrackStats, pal,
                           x, y, w, h, dpi):
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(canvas)
    is_dark = pal["bg"] in ("#0d0d0d", "#0a1628", "#0f1a0f")
    text_color = (255, 255, 255) if is_dark else (30, 30, 30)
    muted_color = (140, 140, 140) if is_dark else (110, 110, 110)
    accent = _hex_to_rgb(pal["track_cmap"][0])

    val_size = round(dpi * 0.32)
    lbl_size = round(dpi * 0.14)

    try:
        font_val = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                      val_size)
        font_lbl = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc",
                                      lbl_size)
    except Exception:
        font_val = ImageFont.load_default()
        font_lbl = ImageFont.load_default()

    items = [
        (f"{stats.distance_km:.1f} km", "DISTANCE"),
        (f"{stats.elevation_gain_m:.0f} m", "ELEVATION GAIN"),
        (f"{stats.elevation_loss_m:.0f} m", "ELEVATION LOSS"),
    ]

    # Only show moving time if we have real data
    if stats.moving_time_s and stats.moving_time_s > 0:
        items.append((_fmt_time(stats.moving_time_s), "MOVING TIME"))

    if stats.max_elevation_m is not None:
        # Show max elevation only if meaningfully above sea level
        label = "MAX ELEVATION"
        val = f"{stats.max_elevation_m:.0f} m"
        items.append((val, label))

    n = len(items)
    col_w = w // n

    # Separator line above stats
    line_y = y + round(dpi * 0.04)
    draw.rectangle([x, line_y, x + w, line_y + round(dpi * 0.01)],
                   fill=(*_hex_to_rgb(pal["border"]), 200))

    for i, (value, label) in enumerate(items):
        cx = x + col_w * i + col_w // 2

        # Accent dot
        dot_y = y + round(dpi * 0.12)
        draw.ellipse(
            [cx - round(dpi * 0.04), dot_y,
             cx + round(dpi * 0.04), dot_y + round(dpi * 0.08)],
            fill=accent,
        )

        # Value
        val_y = dot_y + round(dpi * 0.12)
        bbox = draw.textbbox((0, 0), value, font=font_val)
        vw = bbox[2] - bbox[0]
        draw.text((cx - vw // 2, val_y), value, font=font_val, fill=text_color)

        # Label
        lbl_y = val_y + val_size + round(dpi * 0.04)
        bbox2 = draw.textbbox((0, 0), label, font=font_lbl)
        lw = bbox2[2] - bbox2[0]
        draw.text((cx - lw // 2, lbl_y), label, font=font_lbl, fill=muted_color)

        # Vertical divider
        if i < n - 1:
            div_x = x + col_w * (i + 1)
            draw.rectangle(
                [div_x, y + round(dpi * 0.1),
                 div_x + round(dpi * 0.008),
                 y + h - round(dpi * 0.1)],
                fill=(*_hex_to_rgb(pal["border"]), 180),
            )


def _draw_footer_on_canvas(canvas, pal, x, y, w, h, dpi):
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(canvas)
    is_dark = pal["bg"] in ("#0d0d0d", "#0a1628", "#0f1a0f")
    muted_color = (80, 80, 80) if is_dark else (160, 160, 160)

    sz = round(dpi * 0.11)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz)
    except Exception:
        font = ImageFont.load_default()

    line_y = y + round(dpi * 0.06)
    draw.rectangle([x, line_y, x + w, line_y + round(dpi * 0.008)],
                   fill=muted_color)

    text = "Generated with GPX Poster Generator"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((x + w // 2 - tw // 2, line_y + round(dpi * 0.06)),
              text, font=font, fill=muted_color)


def _save_pdf(canvas: Image.Image, path: Path, pw: int, ph: int):
    """Save the PIL canvas as a PDF page via reportlab."""
    from reportlab.lib.pagesizes import landscape
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.units import mm

    # B2: 500×707 mm
    PAGE_W = 500 * mm
    PAGE_H = 707 * mm

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", dpi=(POSTER_DPI, POSTER_DPI))
    buf.seek(0)

    c = rl_canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.drawInlineImage(Image.open(buf), 0, 0,
                      width=PAGE_W, height=PAGE_H)
    c.save()
