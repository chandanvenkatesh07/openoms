"""Domain models for OpenOMS v0.1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AliasModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


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


class OrderLine(AliasModel):
    order_line_key: str = Field(default_factory=lambda: str(uuid4()), alias="OrderLineKey")
    prime_line_no: str = Field(default="1", alias="PrimeLineNo")
    sku: str = Field(alias="ItemID")
    quantity: int = Field(gt=0, alias="OrderedQty")
    unit_price: float = Field(ge=0, alias="UnitPrice")
    line_type: LineType = Field(default=LineType.SHIP, alias="FulfillmentType")
    ship_node: Optional[str] = Field(default=None, alias="ShipNode")

    @property
    def line_id(self) -> str:
        return self.order_line_key


class Order(AliasModel):
    order_header_key: str = Field(default_factory=lambda: str(uuid4()), alias="OrderHeaderKey")
    order_no: str = Field(default_factory=lambda: f"A{str(uuid4().int)[:8]}", alias="OrderNo")
    enterprise_code: str = Field(default="DEFAULT", alias="EnterpriseCode")
    seller_organization_code: str = Field(default="DEFAULT", alias="SellerOrganizationCode")
    document_type: str = Field(default="0001", alias="DocumentType")
    customer_id: str = Field(alias="BuyerUserId")
    customer_type: CustomerType = Field(default=CustomerType.CONSUMER, alias="CustomerType")
    shipping_zip: str = Field(min_length=5, max_length=10, alias="ShipToZipCode")
    channel: str = Field(default="WEB", alias="EntryType")
    lines: List[OrderLine] = Field(min_length=1, alias="OrderLines")
    requested_delivery_date: Optional[str] = Field(default=None, alias="ReqDeliveryDate")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="OrderDate")

    @property
    def order_id(self) -> str:
        return self.order_header_key


class Node(AliasModel):
    node_id: str
    node_type: NodeType
    zip_code: str
    lat: float
    lon: float
    capacity_units_per_day: int = Field(gt=0)
    cost_to_ship_factor: float = Field(gt=0)
    supports_ship: bool = True


class InventoryRecord(AliasModel):
    sku: str
    node_id: str
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0, default=0)
    safety_stock: int = Field(ge=0, default=0)

    @property
    def available(self) -> int:
        return max(self.on_hand - self.reserved - self.safety_stock, 0)


class Reservation(AliasModel):
    reservation_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    line_id: str
    sku: str
    node_id: str
    quantity: int = Field(gt=0)
    status: str = "held"
    expires_at: datetime
    idempotency_key: str


class PromiseWindow(AliasModel):
    p50_date: str
    p80_date: str
    p95_date: str
    confidence: float = Field(ge=0, le=1)
    method: str = "deterministic"


class Shipment(AliasModel):
    node_id: str
    node_type: NodeType
    line_ids: List[str]
    carrier: str
    promise: PromiseWindow


class SourcingDecision(AliasModel):
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


class InventoryQuery(AliasModel):
    sku: str
    near_zip: Optional[str] = None
    radius_miles: int = Field(default=50, gt=0)


class InventoryView(AliasModel):
    node_id: str
    node_type: NodeType
    sku: str
    on_hand: int
    available: int
    distance_miles: float


class ReserveRequest(AliasModel):
    sku: str
    node_id: str
    quantity: int = Field(gt=0)
    idempotency_key: str
    ttl_seconds: int = Field(default=900, gt=0)
    order_id: Optional[str] = None
    line_id: Optional[str] = None


class ExplainDecisionRequest(AliasModel):
    decision_id: str
    audience: str = "customer"


# ---------------------------------------------------------------------------
# Agentic feature models
# ---------------------------------------------------------------------------

class RelaxationAttempt(AliasModel):
    """Records one step in a constraint-relaxation loop."""
    step: int
    param: str
    value: Union[int, float]
    outcome: str  # "INFEASIBLE" | "OPTIMAL" | "FEASIBLE"
    detail: str = ""


class RelaxationResult(AliasModel):
    """Returned by relax_and_source — decision plus the relaxation history."""
    decision: SourcingDecision
    attempts: List[RelaxationAttempt]
    original_constraints_met: bool
    winning_radius_miles: Optional[int] = None
    agent_summary: str


class SourcingOption(AliasModel):
    """One policy-profile option, returned by get_sourcing_options."""
    option_id: str
    label: str
    description: str
    decision: SourcingDecision
    pros: List[str]
    cons: List[str]


class ResourcingChangeLine(AliasModel):
    """Per-line delta between two sourcing decisions."""
    line_id: str
    sku: str
    old_node_id: str
    new_node_id: str
    old_distance_miles: float
    new_distance_miles: float
    reason: str   # "inventory_depleted" | "reoptimized" | "node_unavailable"
    explanation: str


class ResourcingDiff(AliasModel):
    """Structured diff between an original decision and a re-sourced decision."""
    old_decision_id: str
    new_decision_id: str
    order_id: str
    changed_lines: List[ResourcingChangeLine]
    unchanged_line_ids: List[str]
    split_count_delta: int   # new − old; negative = fewer splits after re-source
    agent_summary: str
