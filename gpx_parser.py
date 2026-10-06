"""GPX file parser — extracts track points and basic statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import gpxpy


@dataclass
class TrackStats:
    name: str
    distance_km: float
    elevation_gain_m: float
    elevation_loss_m: float
    min_elevation_m: Optional[float]
    max_elevation_m: Optional[float]
    moving_time_s: Optional[float]


@dataclass
class TrackData:
    lats: List[float] = field(default_factory=list)
    lons: List[float] = field(default_factory=list)
    elevations: List[Optional[float]] = field(default_factory=list)
    stats: Optional[TrackStats] = None

    @property
    def bounds(self):
        return (min(self.lats), max(self.lats), min(self.lons), max(self.lons))


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_gpx(path: str | Path) -> TrackData:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        gpx = gpxpy.parse(fh)

    lats, lons, elevs = [], [], []

    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                lats.append(pt.latitude)
                lons.append(pt.longitude)
                elevs.append(pt.elevation)

    # Also include waypoints if no tracks found
    if not lats:
        for rte in gpx.routes:
            for pt in rte.points:
                lats.append(pt.latitude)
                lons.append(pt.longitude)
                elevs.append(pt.elevation)

    if not lats:
        raise ValueError("No track points found in GPX file.")

    # Basic stats
    dist = sum(
        _haversine_km(lats[i], lons[i], lats[i + 1], lons[i + 1])
        for i in range(len(lats) - 1)
    )

    gain = loss = 0.0
    valid_elevs = [e for e in elevs if e is not None]
    for i in range(1, len(valid_elevs)):
        diff = valid_elevs[i] - valid_elevs[i - 1]
        if diff > 0:
            gain += diff
        else:
            loss += abs(diff)

    track_name = (
        gpx.tracks[0].name
        if gpx.tracks and gpx.tracks[0].name
        else path.stem.replace("_", " ").replace("-", " ").title()
    )

    moving_time = None
    if gpx.tracks:
        md = gpx.tracks[0].get_moving_data()
        if md:
            moving_time = md.moving_time

    stats = TrackStats(
        name=track_name,
        distance_km=round(dist, 2),
        elevation_gain_m=round(gain, 1),
        elevation_loss_m=round(loss, 1),
        min_elevation_m=round(min(valid_elevs), 1) if valid_elevs else None,
        max_elevation_m=round(max(valid_elevs), 1) if valid_elevs else None,
        moving_time_s=moving_time,
    )

    return TrackData(lats=lats, lons=lons, elevations=elevs, stats=stats)
