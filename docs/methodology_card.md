# Methodology Card

## Hypotheses
- **H0:** At Zipf alpha = 1.0 and cache size = 100 (1 % of 10 000 keys), the relative Hit Rate gain of LFU over LRU, (HR_LFU − HR_LRU) / HR_LRU, is below 15 %.
- **H1:** The relative gain is ≥ 15 % (expected 15–20 %).
- Decision rule: reject H0 if the lower bound of the 95 % bootstrap CI of the paired relative gain (10 seeds) is ≥ 15 %.

## Variables Matrix
| Type | Variable | Values / unit |
|---|---|---|
| Independent | Eviction policy | LRU, LFU |
| Independent | Cache size | 100, 500, 1000 items |
| Independent | Zipf exponent alpha | 0.0 (uniform control), 0.6, 0.8, 1.0, 1.2 |
| Dependent | Cache Hit Rate | % of measured requests |
| Dependent | Mean backend response time | ms/request (hit 0.05 ms, miss 5.05 ms in simulated model) |
| Controlled | Key space | 10 000 keys |
| Controlled | Requests per run | 100 000 (first 20 % warm-up, discarded) |
| Controlled | Trace per seed | identical for both policies (paired design) |
| Controlled | Seeds | 0–9 |
| Controlled | Environment | Python 3.12.7, numpy 2.4.4, PyYAML 6.0.3, matplotlib 3.10.8 |

## Metrics
- **Primary:** Cache Hit Rate (%) and its relative gain LFU vs LRU.
- **Secondary:** mean backend response time (ms).
- **Guardrails:** (1) cache never exceeds capacity (unit-tested); (2) identical trace for both policies; (3) per-request policy overhead measured separately in the SQLite backend mode; (4) uniform workload (alpha = 0) must show no LFU advantage.

## Baseline
LRU (standard algorithm). Additional reference: no cache (Hit Rate 0 %, latency = DB latency).

## Threats to Validity
- Independent-reference model has no temporal locality or popularity drift, which favours LFU.
- LFU here uses in-cache counters (reset on eviction); "perfect LFU" with global counters may differ.
- Latency in the default backend is modelled, not measured.
