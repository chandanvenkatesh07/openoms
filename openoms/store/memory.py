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
    NodeType,
    Reservation,
    ReserveRequest,
    SourcingDecision,
)
from openoms.models.events import DecisionEvent


# Destination-side ZIP lookup for distance and promise calculations.
# Node distances use node.lat/lon directly — no ZIP lookup needed for origin.
ZIP_COORDS: dict[str, tuple[float, float]] = {
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
    "29201": (34.0007, -81.0348),
    "35203": (33.5186, -86.8104),
    "40202": (38.2527, -85.7585),
    "43215": (39.9612, -82.9988),
    "45202": (39.1031, -84.5120),
    "46202": (39.7684, -86.1581),
    "49503": (42.9634, -85.6681),
    "53202": (43.0389, -87.9065),
    "68102": (41.2565, -95.9345),
    "70112": (29.9511, -90.0715),
    "73102": (35.4676, -97.5164),
    "78201": (29.4241, -98.4936),
    "83702": (43.6150, -116.2023),
    "85003": (33.4484, -112.0740),
    "85701": (32.2226, -110.9747),
    "87102": (35.0844, -106.6504),
    "89101": (36.1716, -115.1391),
    "92101": (32.7157, -117.1611),
    "92501": (33.9806, -117.3755),
    "93706": (36.7378, -119.7871),
    "95814": (38.5816, -121.4944),
    "95110": (37.3382, -121.8863),
    "98108": (47.5480, -122.2934),
    "99201": (47.6587, -117.4260),
    "30354": (33.6490, -84.4430),
    "32206": (30.3501, -81.6480),
    "33602": (27.9506, -82.4572),
    "38105": (35.1495, -90.0490),
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 3958.8 * 2 * atan2(sqrt(a), sqrt(1 - a))


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
        dest = ZIP_COORDS.get(near_zip) if near_zip else None
        views: list[InventoryView] = []
        for (item_sku, node_id), record in self.inventory.items():
            if item_sku != sku:
                continue
            node = self.nodes[node_id]
            distance = _haversine(node.lat, node.lon, dest[0], dest[1]) if dest else 0.0
            if distance <= radius_miles:
                views.append(
                    InventoryView(
                        node_id=node_id,
                        node_type=node.node_type,
                        sku=sku,
                        on_hand=record.on_hand,
                        available=record.available,
                        distance_miles=round(distance, 1),
                    )
                )
        return sorted(views, key=lambda v: v.distance_miles)

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


def build_seed_store() -> MemoryStore:
    """Small 5-node store used for unit tests and the quickstart demo."""
    store = MemoryStore()
    nodes = [
        Node(node_id="dc-east", node_type=NodeType.DC, zip_code="10001", lat=40.7506, lon=-73.9972, capacity_units_per_day=1000, cost_to_ship_factor=1.0),
        Node(node_id="dc-south", node_type=NodeType.DC, zip_code="30301", lat=33.7525, lon=-84.3915, capacity_units_per_day=900, cost_to_ship_factor=1.1),
        Node(node_id="store-chi", node_type=NodeType.STORE, zip_code="60601", lat=41.8864, lon=-87.6186, capacity_units_per_day=200, cost_to_ship_factor=0.9),
        Node(node_id="store-dal", node_type=NodeType.STORE, zip_code="75201", lat=32.7876, lon=-96.7994, capacity_units_per_day=180, cost_to_ship_factor=0.95),
        Node(node_id="dc-west", node_type=NodeType.DC, zip_code="90001", lat=33.9739, lon=-118.2487, capacity_units_per_day=950, cost_to_ship_factor=1.2),
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
