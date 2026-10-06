"""GPX Poster Designer — Streamlit web UI.

Deploy:  streamlit run app.py
"""

from __future__ import annotations

import io
import time
import streamlit as st
from PIL import Image

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GPX Poster Designer",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏃 GPX Poster Designer")
st.caption("Upload a GPX file from Strava or Garmin and generate a print-ready B2 poster.")

# ── Session state defaults ────────────────────────────────────────────────────
DEFAULTS = dict(
    title="Półmaraton\nGdańsk",
    date="27.09.26",
    runner_name="Twoje Imię Nazwisko",
    bib="0000",
    pace="0:00",
    finish_time="0:00:00",
    bg_color="#4a86b8",
    track_color="#d4c84a",
    meta_color="#c8dce8",
    line_width=28,
    km_every=5.0,
    title_scale=1.0,
    date_scale=1.0,
    name_scale=1.0,
    meta_scale=1.0,
    time_scale=1.0,
    border_scale=1.0,
    title_y_offset=0.0,
    date_y_offset=0.0,
    name_y_offset=0.0,
    km_markers_visible=True,
    km_marker_size=1.0,
    km_marker_color="#000000",
    start_dot_visible=True,
    start_dot_size=1.0,
    start_dot_color="#ffffff",
    finish_dot_visible=True,
    finish_dot_size=1.0,
    finish_dot_color="#ffffff",
)

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar controls ──────────────────────────────────────────────────────────
sb = st.sidebar

# GPX upload
sb.header("📂 GPX File")
gpx_file = sb.file_uploader("Upload GPX", type=["gpx"], label_visibility="collapsed")

sb.divider()

# ── Text content ──────────────────────────────────────────────────────────────
sb.header("📄 Text Content")
st.session_state.title       = sb.text_area("Event title  (use \\n for new line)",
                                             value=st.session_state.title, height=68)
st.session_state.date        = sb.text_input("Date",        value=st.session_state.date)
st.session_state.runner_name = sb.text_input("Runner name", value=st.session_state.runner_name)
st.session_state.bib         = sb.text_input("BIB number",  value=st.session_state.bib)
st.session_state.pace        = sb.text_input("Pace (e.g. 5:12)",       value=st.session_state.pace)
st.session_state.finish_time = sb.text_input("Finish time (e.g. 1:49:33)", value=st.session_state.finish_time)

sb.divider()

# ── Colours ───────────────────────────────────────────────────────────────────
sb.header("🎨 Colours")
st.session_state.bg_color    = sb.color_picker("Background",   value=st.session_state.bg_color)
st.session_state.track_color = sb.color_picker("Track",        value=st.session_state.track_color)
st.session_state.meta_color  = sb.color_picker("BIB / Pace",   value=st.session_state.meta_color)

sb.divider()

# ── Track ─────────────────────────────────────────────────────────────────────
sb.header("📏 Track")
st.session_state.line_width = sb.slider("Line width (px)", 5, 80,
                                         value=st.session_state.line_width, step=1)

sb.divider()

# ── KM Markers ────────────────────────────────────────────────────────────────
sb.header("📍 KM Markers")
st.session_state.km_markers_visible = sb.checkbox("Show KM markers",
                                                    value=st.session_state.km_markers_visible)
st.session_state.km_every       = sb.slider("Every (km)",    1.0, 10.0,
                                             value=st.session_state.km_every, step=0.5)
st.session_state.km_marker_size = sb.slider("Size (×)",      0.2, 3.0,
                                             value=st.session_state.km_marker_size, step=0.1)
st.session_state.km_marker_color = sb.color_picker("Marker colour",
                                                     value=st.session_state.km_marker_color)

sb.divider()

# ── Start & Finish Dots ───────────────────────────────────────────────────────
sb.header("🏁 Start & Finish Dots")
st.session_state.start_dot_visible = sb.checkbox("Show Start dot",
                                                   value=st.session_state.start_dot_visible)
st.session_state.start_dot_size   = sb.slider("Start dot size (×)", 0.2, 4.0,
                                               value=st.session_state.start_dot_size, step=0.1)
st.session_state.start_dot_color  = sb.color_picker("Start dot colour",
                                                      value=st.session_state.start_dot_color)

st.session_state.finish_dot_visible = sb.checkbox("Show Finish dot",
                                                    value=st.session_state.finish_dot_visible)
st.session_state.finish_dot_size   = sb.slider("Finish dot size (×)", 0.2, 4.0,
                                                value=st.session_state.finish_dot_size, step=0.1)
st.session_state.finish_dot_color  = sb.color_picker("Finish dot colour",
                                                       value=st.session_state.finish_dot_color)

sb.divider()

# ── Font sizes ────────────────────────────────────────────────────────────────
sb.header("🔤 Font Sizes  (× default)")
st.session_state.title_scale  = sb.slider("Title",       0.4, 2.0,
                                           value=st.session_state.title_scale,  step=0.05)
st.session_state.date_scale   = sb.slider("Date",        0.4, 2.0,
                                           value=st.session_state.date_scale,   step=0.05)
st.session_state.name_scale   = sb.slider("Name",        0.4, 2.0,
                                           value=st.session_state.name_scale,   step=0.05)
st.session_state.meta_scale   = sb.slider("BIB / Pace",  0.4, 2.0,
                                           value=st.session_state.meta_scale,   step=0.05)
st.session_state.time_scale   = sb.slider("Finish time", 0.4, 2.0,
                                           value=st.session_state.time_scale,   step=0.05)

sb.divider()

# ── Text Y-position ───────────────────────────────────────────────────────────
sb.header("↕ Text Y-Position  (↑ neg / ↓ pos)")
st.session_state.title_y_offset = sb.slider("Title offset",  -0.15, 0.15,
                                              value=st.session_state.title_y_offset, step=0.005,
                                              format="%.3f")
st.session_state.date_y_offset  = sb.slider("Date offset",   -0.15, 0.15,
                                              value=st.session_state.date_y_offset,  step=0.005,
                                              format="%.3f")
st.session_state.name_y_offset  = sb.slider("Name offset",   -0.15, 0.15,
                                              value=st.session_state.name_y_offset,  step=0.005,
                                              format="%.3f")

sb.divider()

# ── Layout ────────────────────────────────────────────────────────────────────
sb.header("🖼 Layout")
st.session_state.border_scale = sb.slider("White border width", 0.0, 3.0,
                                           value=st.session_state.border_scale, step=0.1)

sb.divider()
if sb.button("↺  Reset all to defaults", use_container_width=True):
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.rerun()

# ── Main area: preview + export ───────────────────────────────────────────────

if gpx_file is None:
    st.info("👈  Upload a GPX file in the sidebar to get started.")
    st.stop()

# Parse GPX (cache by filename + size to avoid re-parsing on every slider move)
@st.cache_data(show_spinner="Parsing GPX…")
def _parse(name: str, size: int, data: bytes):
    import tempfile, os
    from gpx_parser import parse_gpx
    with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        return parse_gpx(tmp)
    finally:
        os.unlink(tmp)

gpx_bytes = gpx_file.read()
track = _parse(gpx_file.name, len(gpx_bytes), gpx_bytes)
s = track.stats
st.caption(
    f"**{gpx_file.name}** · {s.distance_km:.1f} km · "
    f"+{s.elevation_gain_m:.0f} m · {len(track.lats):,} pts"
)

# ── Render ────────────────────────────────────────────────────────────────────
def _collect_kwargs() -> dict:
    ss = st.session_state
    return dict(
        event_title  = ss.title,
        event_date   = ss.date,
        runner_name  = ss.runner_name,
        bib          = ss.bib,
        pace         = ss.pace,
        finish_time  = ss.finish_time,
        bg_color     = ss.bg_color,
        track_color  = ss.track_color,
        meta_color   = ss.meta_color,
        line_width   = float(ss.line_width),
        km_every     = float(ss.km_every),
        title_scale  = ss.title_scale,
        date_scale   = ss.date_scale,
        name_scale   = ss.name_scale,
        meta_scale   = ss.meta_scale,
        time_scale   = ss.time_scale,
        border_scale = ss.border_scale,
        title_y_offset = ss.title_y_offset,
        date_y_offset  = ss.date_y_offset,
        name_y_offset  = ss.name_y_offset,
        km_markers_visible = ss.km_markers_visible,
        km_marker_size     = ss.km_marker_size,
        km_marker_color    = ss.km_marker_color,
        start_dot_visible  = ss.start_dot_visible,
        start_dot_size     = ss.start_dot_size,
        start_dot_color    = ss.start_dot_color,
        finish_dot_visible = ss.finish_dot_visible,
        finish_dot_size    = ss.finish_dot_size,
        finish_dot_color   = ss.finish_dot_color,
    )

with st.spinner("Rendering poster…"):
    t0 = time.time()
    from poster_race import generate_race_poster_image
    preview_img: Image.Image = generate_race_poster_image(
        track=track,
        preview_size=(500, 707),
        **_collect_kwargs(),
    )
    elapsed = time.time() - t0

st.image(preview_img, caption=f"Preview (rendered in {elapsed:.1f}s)", use_container_width=True)

# ── Export buttons ────────────────────────────────────────────────────────────
st.subheader("⬇ Export")
col_png, col_pdf = st.columns(2)

with col_png:
    buf_png = io.BytesIO()
    with st.spinner("Preparing PNG…"):
        from poster_race import generate_race_poster_image, POSTER_DPI, PW, PH
        full_img = generate_race_poster_image(track=track, **_collect_kwargs())
        full_img.save(buf_png, format="PNG", dpi=(POSTER_DPI, POSTER_DPI))
    st.download_button(
        label="🖼  Download PNG  (B2 · 300 DPI)",
        data=buf_png.getvalue(),
        file_name="poster.png",
        mime="image/png",
        use_container_width=True,
    )

with col_pdf:
    buf_pdf = io.BytesIO()
    with st.spinner("Preparing PDF…"):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as rl_canvas
        PAGE_W, PAGE_H = 500 * mm, 707 * mm
        tmp_png = io.BytesIO()
        full_img.save(tmp_png, format="PNG", dpi=(POSTER_DPI, POSTER_DPI))
        tmp_png.seek(0)
        from PIL import Image as _Img
        c = rl_canvas.Canvas(buf_pdf, pagesize=(PAGE_W, PAGE_H))
        c.drawInlineImage(_Img.open(tmp_png), 0, 0, width=PAGE_W, height=PAGE_H)
        c.save()
    st.download_button(
        label="📄  Download PDF  (B2 · print-ready)",
        data=buf_pdf.getvalue(),
        file_name="poster.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
