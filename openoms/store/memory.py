"""In-memory repositories for local development and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Dict, List

from openoms.models.domain import (
    ExplainDecisionRequest,
    InventoryRecord,
    InventoryView,
    Node,
    Order,
    Reservation,
    ReserveRequest,
    SourcingDecision,
)
from openoms.models.events import DecisionEvent


ZIP_COORDS = {
    "10001": (40.7506, -73.9972),
    "02108": (42.3570, -71.0637),
    "19103": (39.9526, -75.1742),
    "20001": (38.9101, -77.0147),
    "21201": (39.2946, -76.6255),
    "28202": (35.2271, -80.8431),
    "33131": (25.7680, -80.1890),
    "30301": (33.7525, -84.3915),
    "37203": (36.1520, -86.7830),
    "48226": (42.3314, -83.0458),
    "55401": (44.9833, -93.2667),
    "60601": (41.8864, -87.6186),
    "63101": (38.6312, -90.1922),
    "64106": (39.0997, -94.5786),
    "75201": (32.7876, -96.7994),
    "77002": (29.7569, -95.3625),
    "80202": (39.7528, -104.9992),
    "85004": (33.4518, -112.0682),
    "90001": (33.9739, -118.2487),
    "94103": (37.7725, -122.4091),
    "94105": (37.7898, -122.3942),
    "97205": (45.5200, -122.6819),
    "98101": (47.6101, -122.3344),
    "84101": (40.7608, -111.8910),
}


class NotFoundError(ValueError):
    """Raised when a record does not exist."""


class InsufficientInventoryError(ValueError):
    """Raised when a reservation cannot be satisfied."""


@dataclass
class MemoryStore:
    nodes: Dict[str, Node] = field(default_factory=dict)
    inventory: Dict[tuple[str, str], InventoryRecord] = field(default_factory=dict)
    reservations_by_key: Dict[str, Reservation] = field(default_factory=dict)
    reservations_by_id: Dict[str, Reservation] = field(default_factory=dict)
    decisions: Dict[str, SourcingDecision] = field(default_factory=dict)
    events: List[DecisionEvent] = field(default_factory=list)

    def get_inventory(self, sku: str, near_zip: str | None, radius_miles: int) -> list[InventoryView]:
        views: list[InventoryView] = []
        for (item_sku, node_id), record in self.inventory.items():
            if item_sku != sku:
                continue
            node = self.nodes[node_id]
            distance = self._distance_miles(node.zip_code, near_zip)
            if distance <= radius_miles:
                views.append(
                    InventoryView(
                        node_id=node_id,
                        node_type=node.node_type,
                        on_hand=record.on_hand,
                        available=record.available,
                        distance_miles=round(distance, 1),
                    )
                )
        return sorted(views, key=lambda item: item.distance_miles)

    def reserve(self, request: ReserveRequest) -> Reservation:
        existing = self.reservations_by_key.get(request.idempotency_key)
        if existing is not None:
            return existing
        record = self.inventory.get((request.sku, request.node_id))
        if record is None:
            raise NotFoundError(f"inventory missing for {request.sku} at {request.node_id}")
        if record.available < request.quantity:
            raise InsufficientInventoryError(f"insufficient inventory for {request.sku} at {request.node_id}")
        record.reserved += request.quantity
        reservation = Reservation(
            order_id=request.order_id or "manual",
            line_id=request.line_id or "manual",
            sku=request.sku,
            node_id=request.node_id,
            quantity=request.quantity,
            expires_at=datetime.utcnow() + timedelta(seconds=request.ttl_seconds),
            idempotency_key=request.idempotency_key,
        )
        self.reservations_by_key[request.idempotency_key] = reservation
        self.reservations_by_id[reservation.reservation_id] = reservation
        return reservation

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        reservation = self.reservations_by_id.get(reservation_id)
        if reservation is None:
            raise NotFoundError(f"reservation {reservation_id} not found")
        if reservation.status == "cancelled":
            return reservation
        record = self.inventory[(reservation.sku, reservation.node_id)]
        record.reserved = max(record.reserved - reservation.quantity, 0)
        reservation.status = "cancelled"
        return reservation

    def save_decision(self, decision: SourcingDecision) -> None:
        self.decisions[decision.decision_id] = decision

    def get_decision(self, request: ExplainDecisionRequest) -> SourcingDecision:
        decision = self.decisions.get(request.decision_id)
        if decision is None:
            raise NotFoundError(f"decision {request.decision_id} not found")
        return decision

    def append_event(self, event: DecisionEvent) -> None:
        self.events.append(event)

    def seed(self, nodes: list[Node], inventory: list[InventoryRecord]) -> None:
        for node in nodes:
            self.nodes[node.node_id] = node
        for record in inventory:
            self.inventory[(record.sku, record.node_id)] = record

    def _distance_miles(self, origin_zip: str, dest_zip: str | None) -> float:
        if dest_zip is None:
            return 0.0
        origin = ZIP_COORDS.get(origin_zip)
        dest = ZIP_COORDS.get(dest_zip)
        if origin is None or dest is None:
            return 9999.0
        lat1, lon1 = map(radians, origin)
        lat2, lon2 = map(radians, dest)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return 3958.8 * c


def build_seed_store() -> MemoryStore:
    store = MemoryStore()
    nodes = [
        Node(node_id="dc-east", node_type="dc", zip_code="10001", lat=40.7506, lon=-73.9972, capacity_units_per_day=1000, cost_to_ship_factor=1.0),
        Node(node_id="dc-south", node_type="dc", zip_code="30301", lat=33.7525, lon=-84.3915, capacity_units_per_day=900, cost_to_ship_factor=1.1),
        Node(node_id="store-chi", node_type="store", zip_code="60601", lat=41.8864, lon=-87.6186, capacity_units_per_day=200, cost_to_ship_factor=0.9),
        Node(node_id="store-dal", node_type="store", zip_code="75201", lat=32.7876, lon=-96.7994, capacity_units_per_day=180, cost_to_ship_factor=0.95),
        Node(node_id="dc-west", node_type="dc", zip_code="90001", lat=33.9739, lon=-118.2487, capacity_units_per_day=950, cost_to_ship_factor=1.2),
    ]
    inventory = [
        InventoryRecord(sku="HAMMER-001", node_id="dc-east", on_hand=20, reserved=0),
        InventoryRecord(sku="HAMMER-001", node_id="store-chi", on_hand=4, reserved=0),
        InventoryRecord(sku="HAMMER-001", node_id="store-dal", on_hand=2, reserved=0),
        InventoryRecord(sku="PAINT-RED-1G", node_id="dc-south", on_hand=10, reserved=0),
        InventoryRecord(sku="PAINT-RED-1G", node_id="dc-west", on_hand=7, reserved=0),
    ]
    store.seed(nodes=nodes, inventory=inventory)
    return store
