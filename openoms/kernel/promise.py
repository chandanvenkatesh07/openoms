"""Deterministic promise-date engine for v0.1."""

from __future__ import annotations

from datetime import date, timedelta

from openoms.store.memory import ZIP_COORDS
from openoms.models.domain import PromiseWindow


def compute_promise(origin_zip: str, destination_zip: str) -> PromiseWindow:
    """Compute a simple promise window from known lane roughness."""
    if origin_zip == destination_zip:
        transit_days = 1
    else:
        origin = ZIP_COORDS.get(origin_zip)
        dest = ZIP_COORDS.get(destination_zip)
        if origin is None or dest is None:
            transit_days = 5
        else:
            transit_days = 2 if abs(origin[0] - dest[0]) < 5 else 4
    start = date.today() + timedelta(days=transit_days)
    return PromiseWindow(
        p50_date=start.isoformat(),
        p80_date=(start + timedelta(days=1)).isoformat(),
        p95_date=(start + timedelta(days=2)).isoformat(),
        confidence=0.8,
    )
