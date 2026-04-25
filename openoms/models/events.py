"""Event models for append-only logging."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DecisionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
