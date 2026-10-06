"""Route map renderer using pure Matplotlib (no external tile server needed).

Draws the GPX track on a clean dark background with grid lines,
returns a high-resolution Figure ready for embedding in the poster.
"""

from __future__ import annotations

import math
from typing import Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

from gpx_parser import TrackData


# --------------------------------------------------------------------------- #
# Colour palettes                                                              #
# --------------------------------------------------------------------------- #

THEMES = {
    "dark": {
        "bg": "#0d0d0d",
        "track_cmap": ["#ff6b35", "#f7c59f", "#ffffff"],
        "grid": "#1e1e1e",
        "border": "#333333",
    },
    "light": {
        "bg": "#f5f0e8",
        "track_cmap": ["#c0392b", "#e67e22", "#2c3e50"],
        "grid": "#ddd8cc",
        "border": "#b0a898",
    },
    "ocean": {
        "bg": "#0a1628",
        "track_cmap": ["#00d4ff", "#7b68ee", "#ff6ec7"],
        "grid": "#0e1f3a",
        "border": "#1a3a5c",
    },
    "forest": {
        "bg": "#0f1a0f",
        "track_cmap": ["#76c442", "#c8e6a0", "#ffffff"],
        "grid": "#172217",
        "border": "#2a3d2a",
    },
}


def _make_cmap(colors):
    return LinearSegmentedColormap.from_list("track", colors)


def _equal_aspect_padding(
    lat_min, lat_max, lon_min, lon_max, pad_frac=0.08
) -> Tuple[float, float, float, float]:
    """Expand bounds so the route has some breathing room and aspect ratio
    is corrected for the Mercator-like distortion at the given latitude."""
    lat_mid = (lat_min + lat_max) / 2
    cos_lat = math.cos(math.radians(lat_mid))

    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min

    # Normalise spans to the same "degree-equivalent" unit
    # then make the bounding box square in projected space
    lat_deg_per_km = 1 / 111.0
    lon_deg_per_km = 1 / (111.0 * cos_lat) if cos_lat > 0.01 else lat_deg_per_km

    lat_km = lat_span / lat_deg_per_km
    lon_km = lon_span / lon_deg_per_km
    max_km = max(lat_km, lon_km) * (1 + pad_frac * 2)

    lat_half = max_km * lat_deg_per_km / 2
    lon_half = max_km * lon_deg_per_km / 2

    lat_c = (lat_min + lat_max) / 2
    lon_c = (lon_min + lon_max) / 2

    return lat_c - lat_half, lat_c + lat_half, lon_c - lon_half, lon_c + lon_half


def map_aspect_ratio(track: TrackData) -> float:
    """Return width/height pixel ratio for a distortion-free map of this track."""
    lat_min, lat_max, lon_min, lon_max = _equal_aspect_padding(*track.bounds)
    lat_mid = (lat_min + lat_max) / 2
    cos_lat = math.cos(math.radians(lat_mid))
    lat_km = (lat_max - lat_min) * 111.0
    lon_km = (lon_max - lon_min) * 111.0 * cos_lat
    return lon_km / lat_km if lat_km > 0 else 1.0


def render_map(
    track: TrackData,
    theme: str = "dark",
    dpi: int = 300,
    fig_width_in: float = 13.0,
    fig_height_in: float = None,   # if None → derived from aspect ratio
    line_width: float = 1.8,
    color_by: str = "progress",   # "progress" | "elevation" | "solid"
) -> plt.Figure:
    """Return a Matplotlib Figure with the rendered route map.

    The figure is sized so that the track fills it edge-to-edge without any
    blank letterboxing — figsize is derived from the true projected aspect ratio.
    """
    palette = THEMES.get(theme, THEMES["dark"])
    lats = np.array(track.lats)
    lons = np.array(track.lons)
    elevs = np.array(
        [e if e is not None else 0.0 for e in track.elevations],
        dtype=float,
    )

    lat_min, lat_max, lon_min, lon_max = _equal_aspect_padding(*track.bounds)

    # Compute correct figure height from the true projected aspect ratio
    ar = map_aspect_ratio(track)          # lon_km / lat_km  (width / height)
    if fig_height_in is None:
        fig_height_in = fig_width_in / ar

    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), dpi=dpi)
    fig.patch.set_facecolor(palette["bg"])
    ax.set_facecolor(palette["bg"])

    # ---- grid lines -------------------------------------------------------- #
    lat_ticks = np.linspace(lat_min, lat_max, 7)
    lon_ticks = np.linspace(lon_min, lon_max, 7)
    for lt in lat_ticks:
        ax.axhline(lt, color=palette["grid"], linewidth=0.4, zorder=1)
    for ln in lon_ticks:
        ax.axvline(ln, color=palette["grid"], linewidth=0.4, zorder=1)

    # ---- build coloured track segments ------------------------------------- #
    points = np.array([lons, lats]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)

    if color_by == "elevation" and elevs.max() > elevs.min():
        values = (elevs[:-1] + elevs[1:]) / 2
        values = (values - values.min()) / (values.max() - values.min())
    else:  # progress
        values = np.linspace(0, 1, len(segments))

    cmap = _make_cmap(palette["track_cmap"])

    # Shadow / glow pass
    lc_shadow = LineCollection(
        segments, array=values, cmap=cmap,
        linewidth=line_width * 4, alpha=0.15, zorder=2, capstyle="round",
    )
    ax.add_collection(lc_shadow)

    # Main track
    lc = LineCollection(
        segments, array=values, cmap=cmap,
        linewidth=line_width, alpha=0.95, zorder=3, capstyle="round",
    )
    ax.add_collection(lc)

    # ---- start / end markers ---------------------------------------------- #
    # Small fixed-size dots — don't overwhelm the track line
    marker_s = max(30, round(fig_width_in * 8))
    dot_kw = dict(transform=ax.transData, zorder=5, s=marker_s)
    ax.scatter([lons[0]], [lats[0]], color="#2ecc71", marker="o", **dot_kw,
               edgecolors="white", linewidths=0.8)
    ax.scatter([lons[-1]], [lats[-1]], color="#e74c3c", marker="o", **dot_kw,
               edgecolors="white", linewidths=0.8)

    # ---- axis limits — exact bounding box, no extra aspect correction ------ #
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    # Do NOT call set_aspect("equal") — figsize already encodes the correct ratio

    ax.axis("off")
    fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
    return fig


def render_elevation_profile(
    track: TrackData,
    theme: str = "dark",
    dpi: int = 300,
    fig_width_in: float = 13.0,
    fig_height_in: float = 2.5,
) -> plt.Figure:
    """Return a Matplotlib Figure with the elevation profile."""
    palette = THEMES.get(theme, THEMES["dark"])
    elevs = [e for e in track.elevations if e is not None]
    if not elevs:
        return None

    xs = np.linspace(0, track.stats.distance_km, len(elevs))
    ys = np.array(elevs)

    fig, ax = plt.subplots(figsize=(fig_width_in, fig_height_in), dpi=dpi)
    fig.patch.set_facecolor(palette["bg"])
    ax.set_facecolor(palette["bg"])

    cmap = _make_cmap(palette["track_cmap"])
    # Gradient fill under the profile
    n = len(xs)
    for i in range(n - 1):
        c = cmap(i / n)
        ax.fill_between(xs[i:i + 2], ys.min() - 5, ys[i:i + 2],
                        color=c, alpha=0.6, linewidth=0)

    # Profile line
    points = np.array([xs, ys]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    values = np.linspace(0, 1, len(segments))
    lc = LineCollection(segments, array=values, cmap=cmap,
                        linewidth=2.0, zorder=3)
    ax.add_collection(lc)

    y_pad = (ys.max() - ys.min()) * 0.1 if ys.max() > ys.min() else 5
    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylim(ys.min() - y_pad, ys.max() + y_pad * 1.5)

    tick_color = "#aaaaaa"
    ax.tick_params(colors=tick_color, labelsize=14, length=3, width=0.6,
                   direction="in")
    ax.set_xlabel("Distance (km)", fontsize=16, color=tick_color, labelpad=6)
    ax.set_ylabel("Elevation (m)", fontsize=16, color=tick_color, labelpad=6)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(tick_color)
    for spine in ax.spines.values():
        spine.set_edgecolor(palette["border"])
        spine.set_linewidth(0.6)

    fig.subplots_adjust(left=0.06, right=0.99, top=0.92, bottom=0.22)
    return fig
