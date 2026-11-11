# OpenOMS Sourcing Evaluation

This evaluation measures the existing seeded CP-SAT and greedy implementations. It is synthetic engineering evidence, not production performance evidence.

## Reproduce

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/evaluate_sourcing.py --repetitions 20 --time-limits 200 2000
```

Measured on commit `b661bbf` plus the evaluation script, using Python 3.14.4 on Apple Silicon/macOS 26.5. The dataset contained 200 nodes and 30,522 inventory records. Every scenario was repeated 20 times at the normal service limit (200 ms) and the interactive benchmark limit (2,000 ms).

## Results at the 200 ms service limit

| Scenario | Lines | CP-SAT feasible | CP-SAT p50 / p95 | CP-SAT shipments | Greedy shipments | Weighted-distance tradeoff |
|---|---:|---:|---:|---:|---:|---:|
| Baseline, low split penalty | 50 | 20/20 | 170.2 / 180.1 ms | 6 | 6 | equal at 831.0 mi |
| High consolidation pressure | 50 | 20/20 | 176.9 / 184.2 ms | 3 | 6 | CP-SAT +483.8 mi |
| Constrained inventory | 4 | 20/20 | 1.8 / 2.0 ms | 2 | 3 | CP-SAT +490.8 mi |

Greedy p50 latency was 0.056 ms, 0.058 ms, and 0.005 ms respectively. All 60 CP-SAT runs at 200 ms reported `OPTIMAL`; the same assignments and 100% feasible rate were observed at 2,000 ms.

## Interpretation

- With a low split penalty, joint optimization and nearest-first greedy produced the same six shipments and weighted distance. CP-SAT added latency without improving this scenario.
- With a high split penalty, CP-SAT reduced six shipments to three by accepting 483.8 additional weighted miles. This is the intended policy tradeoff, not a universal quality improvement.
- In the constrained case, greedy committed to the nearest partial stock and used three nodes. CP-SAT saw the cross-line inventory interaction and used two farther nodes.
- The normal 200 ms service limit was sufficient for these cases on this machine, but the result does not establish behavior at enterprise order volume or under concurrent load.

## Coverage and limitations

Measured:

- solver wall time;
- feasible-solution rate;
- shipment/node count;
- weighted assignment distance;
- CP-SAT versus greedy behavior under two policy profiles and constrained inventory.

Not measured:

- concurrent throughput, queueing, or memory use;
- reservation transaction latency or contention;
- promise accuracy against carrier outcomes;
- production solution quality or cost;
- behavior on real inventory distributions;
- automatic recovery after a process or dependency failure.

The evaluator reports environment and dataset metadata in JSON so later results can be compared without presenting one machine's timing as a universal benchmark.
