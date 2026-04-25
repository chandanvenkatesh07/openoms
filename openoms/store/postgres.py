"""Postgres schema and future repository hooks for OpenOMS."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    zip_code TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    capacity_units_per_day INTEGER NOT NULL,
    cost_to_ship_factor DOUBLE PRECISION NOT NULL,
    supports_ship BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS inventory_records (
    sku TEXT NOT NULL,
    node_id TEXT NOT NULL REFERENCES nodes(node_id),
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL DEFAULT 0,
    safety_stock INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sku, node_id)
);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    line_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    node_id TEXT NOT NULL REFERENCES nodes(node_id),
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sourcing_decisions (
    decision_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    total_cost DOUBLE PRECISION NOT NULL,
    split_count INTEGER NOT NULL,
    policy_version_used TEXT NOT NULL,
    reasoning_trace JSONB NOT NULL,
    explanation TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_events (
    event_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL
);
"""
