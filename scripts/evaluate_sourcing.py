"""Repeatable sourcing evaluation for the implemented CP-SAT and greedy paths.

This script uses the repository's existing seeded scenarios. It does not claim
production performance: results describe synthetic data on the machine reported
in the JSON output.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import statistics
import sys
from dataclasses import dataclass
from typing import Callable

from openoms.benchmark import _scenario_1, _scenario_2, _scenario_3
from openoms.kernel.greedy import solve_sourcing_greedy
from openoms.kernel.solver import SolverResult, solve_sourcing
from openoms.seed.hearthline import build_hearthline_store


@dataclass
class Observation:
    feasible: bool
    wall_ms: float | None
    shipments: int | None
    weighted_distance_miles: float | None
    solve_status: str


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return round(ordered[index], 3)


def weighted_distance(result: SolverResult) -> float:
    return round(sum(a.distance_miles * a.quantity for a in result.assignments), 3)


def observe(result: SolverResult) -> Observation:
    return Observation(
        feasible=True,
        wall_ms=result.wall_ms,
        shipments=result.split_count,
        weighted_distance_miles=weighted_distance(result),
        solve_status=result.solve_status,
    )


def summarize(observations: list[Observation]) -> dict:
    feasible = [item for item in observations if item.feasible]
    times = [item.wall_ms for item in feasible if item.wall_ms is not None]
    shipments = [item.shipments for item in feasible if item.shipments is not None]
    distances = [
        item.weighted_distance_miles
        for item in feasible
        if item.weighted_distance_miles is not None
    ]
    statuses: dict[str, int] = {}
    for item in observations:
        statuses[item.solve_status] = statuses.get(item.solve_status, 0) + 1
    return {
        "runs": len(observations),
        "feasible_runs": len(feasible),
        "feasible_rate": round(len(feasible) / len(observations), 4),
        "wall_ms_p50": percentile(times, 0.50),
        "wall_ms_p95": percentile(times, 0.95),
        "shipments_median": statistics.median(shipments) if shipments else None,
        "weighted_distance_miles_median": statistics.median(distances) if distances else None,
        "statuses": statuses,
    }


def build_scenario(builder: Callable, store):
    # Scenario 3 prints an interactive walkthrough; capture it so stdout is JSON.
    with contextlib.redirect_stdout(io.StringIO()):
        values = builder(store)
    label, order, candidates, weights = values[:4]
    return label, order, candidates, weights


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--time-limits", type=int, nargs="+", default=[200, 2000])
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be positive")

    store = build_hearthline_store()
    builders = {
        "s1_baseline_50_lines": _scenario_1,
        "s2_consolidation_50_lines": _scenario_2,
        "s3_constrained_inventory_4_lines": _scenario_3,
    }
    report: dict = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "dataset": {
            "nodes": len(store.nodes),
            "inventory_records": len(store.inventory),
            "synthetic": True,
        },
        "repetitions": args.repetitions,
        "time_limits_ms": args.time_limits,
        "scenarios": {},
    }

    for scenario_id, builder in builders.items():
        label, order, candidates, weights = build_scenario(builder, store)
        greedy_observations: list[Observation] = []
        cp_by_limit: dict[str, list[Observation]] = {
            str(limit): [] for limit in args.time_limits
        }
        for _ in range(args.repetitions):
            greedy_observations.append(observe(solve_sourcing_greedy(order, candidates)))
            for limit in args.time_limits:
                try:
                    result = solve_sourcing(
                        order,
                        candidates,
                        weights=weights,
                        time_limit_ms=limit,
                    )
                    cp_by_limit[str(limit)].append(observe(result))
                except ValueError as exc:
                    cp_by_limit[str(limit)].append(
                        Observation(False, None, None, None, f"ERROR: {exc}")
                    )

        greedy_summary = summarize(greedy_observations)
        cp_summaries = {key: summarize(value) for key, value in cp_by_limit.items()}
        comparisons = {}
        for limit, cp_summary in cp_summaries.items():
            if cp_summary["shipments_median"] is not None:
                comparisons[limit] = {
                    "shipment_reduction_vs_greedy": (
                        greedy_summary["shipments_median"]
                        - cp_summary["shipments_median"]
                    ),
                    "weighted_distance_delta_vs_greedy": round(
                        cp_summary["weighted_distance_miles_median"]
                        - greedy_summary["weighted_distance_miles_median"],
                        3,
                    ),
                }

        report["scenarios"][scenario_id] = {
            "label": label,
            "line_count": len(order.lines),
            "candidate_assignments": sum(len(value) for value in candidates.values()),
            "greedy": greedy_summary,
            "cp_sat_by_time_limit_ms": cp_summaries,
            "comparisons": comparisons,
        }

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
