"""Lightweight HTTP server for the OpenOMS visual playground and demo API."""

from __future__ import annotations

import json
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from openoms.models.domain import ExplainDecisionRequest, InventoryQuery, Order
from openoms.service import OpenOMSService

SERVICE = OpenOMSService()
PLAYGROUND_PATH = Path(__file__).resolve().parent.parent / "docs" / "openoms-playground-live.html"


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class OpenOMSHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "OpenOMSHTTP/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers("application/json")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/playground"}:
            self._serve_playground()
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok", "service": "openoms", "policy_version": SERVICE.policy_version})
            return
        if parsed.path == "/api/config":
            self._send_json({"policy": SERVICE.policy, "seed_nodes": self._seed_nodes()})
            return
        if parsed.path == "/api/explain-decision":
            query = parse_qs(parsed.query)
            decision_id = query.get("decision_id", [None])[0]
            audience = query.get("audience", ["customer"])[0]
            if not decision_id:
                self._send_json({"error": "decision_id is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = SERVICE.explain_decision(ExplainDecisionRequest(decision_id=decision_id, audience=audience))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json(payload)
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if isinstance(body, tuple):
            message, status = body
            self._send_json({"error": message}, status=status)
            return

        if parsed.path == "/api/inventory":
            try:
                request = InventoryQuery.model_validate(body)
                items = SERVICE.get_inventory(request)
            except Exception as exc:  # pragma: no cover - defensive request parsing
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"items": [item.model_dump(mode="json") for item in items]})
            return

        if parsed.path == "/api/source-order":
            order_payload = body.get("order")
            idempotency_key = body.get("idempotency_key") or f"demo-{uuid4()}"
            if order_payload is None:
                self._send_json({"error": "order is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                order = Order.model_validate(order_payload)
                decision = SERVICE.source_order(order, idempotency_key=idempotency_key)
                explanation = SERVICE.explain_decision(
                    ExplainDecisionRequest(decision_id=decision.decision_id, audience="customer")
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                {
                    "decision": decision.model_dump(mode="json", by_alias=True),
                    "explanation": explanation,
                    "inventory_snapshot": self._inventory_snapshot(order.lines[0].sku, order.shipping_zip),
                }
            )
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _serve_playground(self) -> None:
        content = PLAYGROUND_PATH.read_text(encoding="utf-8")
        self.send_response(HTTPStatus.OK)
        self._send_common_headers("text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _read_json_body(self) -> dict[str, Any] | tuple[str, HTTPStatus]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return "missing Content-Length header", HTTPStatus.LENGTH_REQUIRED
        try:
            length = int(raw_length)
        except ValueError:
            return "invalid Content-Length header", HTTPStatus.BAD_REQUEST
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return "request body must be valid JSON", HTTPStatus.BAD_REQUEST
        if not isinstance(data, dict):
            return "request body must be a JSON object", HTTPStatus.BAD_REQUEST
        return data

    def _inventory_snapshot(self, sku: str, near_zip: str) -> list[dict[str, Any]]:
        items = SERVICE.get_inventory(InventoryQuery(sku=sku, near_zip=near_zip, radius_miles=int(SERVICE.policy.get("radius_miles", 150))))
        return [item.model_dump(mode="json") for item in items]

    def _seed_nodes(self) -> list[dict[str, Any]]:
        return [node.model_dump(mode="json") for node in SERVICE.store.nodes.values()]

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=json_default).encode("utf-8")
        self.send_response(status)
        self._send_common_headers("application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")


def main(host: str = "127.0.0.1", port: int = 8011) -> None:
    httpd = ThreadingHTTPServer((host, port), OpenOMSHTTPRequestHandler)
    print(f"OpenOMS API server listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
