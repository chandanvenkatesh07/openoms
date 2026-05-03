"""Deterministic promise-date engine for v0.1."""

from __future__ import annotations

from datetime import date, timedelta

from openoms.store.memory import ZIP_COORDS
from openoms.models.domain import PromiseWindow


def compute_promise(origin_lat: float, origin_lon: float, destination_zip: str) -> PromiseWindow:
    """Compute a deterministic promise window from node coordinates to destination ZIP."""
    dest = ZIP_COORDS.get(destination_zip)
    if dest is None:
        transit_days = 5
    else:
        lat_diff = abs(origin_lat - dest[0])
        lon_diff = abs(origin_lon - dest[1])
        if lat_diff < 3 and lon_diff < 3:
            transit_days = 1
        elif lat_diff < 8 and lon_diff < 15:
            transit_days = 2
        else:
            transit_days = 4
    start = date.today() + timedelta(days=transit_days)
    return PromiseWindow(
        p50_date=start.isoformat(),
        p80_date=(start + timedelta(days=1)).isoformat(),
        p95_date=(start + timedelta(days=2)).isoformat(),
        confidence=0.8,
    )
