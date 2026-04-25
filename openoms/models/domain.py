"""Domain models for OpenOMS v0.1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CustomerType(str, Enum):
    CONSUMER = "consumer"
    PRO = "pro"


class NodeType(str, Enum):
    DC = "dc"
    STORE = "store"


class LineType(str, Enum):
    SHIP = "ship"
    PICKUP = "pickup"
    WILL_CALL = "will_call"
    DELIVERY = "delivery"


class OrderLine(BaseModel):
    line_id: str = Field(default_factory=lambda: str(uuid4()))
    sku: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    line_type: LineType = LineType.SHIP


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    customer_id: str
    customer_type: CustomerType = CustomerType.CONSUMER
    shipping_zip: str = Field(min_length=5, max_length=10)
    channel: str = "web"
    lines: List[OrderLine] = Field(min_length=1)
    requested_delivery_date: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Node(BaseModel):
    node_id: str
    node_type: NodeType
    zip_code: str
    lat: float
    lon: float
    capacity_units_per_day: int = Field(gt=0)
    cost_to_ship_factor: float = Field(gt=0)
    supports_ship: bool = True


class InventoryRecord(BaseModel):
    sku: str
    node_id: str
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0, default=0)
    safety_stock: int = Field(ge=0, default=0)

    @property
    def available(self) -> int:
        return max(self.on_hand - self.reserved - self.safety_stock, 0)


class Reservation(BaseModel):
    reservation_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    line_id: str
    sku: str
    node_id: str
    quantity: int = Field(gt=0)
    status: str = "held"
    expires_at: datetime
    idempotency_key: str


class PromiseWindow(BaseModel):
    p50_date: str
    p80_date: str
    p95_date: str
    confidence: float = Field(ge=0, le=1)
    method: str = "deterministic"


class Shipment(BaseModel):
    node_id: str
    node_type: NodeType
    line_ids: List[str]
    carrier: str
    promise: PromiseWindow


class SourcingDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    shipments: List[Shipment]
    total_cost: float = Field(ge=0)
    split_count: int = Field(ge=1)
    policy_version_used: str
    reasoning_trace: dict
    explanation: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "committed"


class InventoryQuery(BaseModel):
    sku: str
    near_zip: Optional[str] = None
    radius_miles: int = Field(default=50, gt=0)


class InventoryView(BaseModel):
    node_id: str
    node_type: NodeType
    on_hand: int
    available: int
    distance_miles: float


class ReserveRequest(BaseModel):
    sku: str
    node_id: str
    quantity: int = Field(gt=0)
    idempotency_key: str
    ttl_seconds: int = Field(default=900, gt=0)
    order_id: Optional[str] = None
    line_id: Optional[str] = None


class ExplainDecisionRequest(BaseModel):
    decision_id: str
    audience: str = "customer"
