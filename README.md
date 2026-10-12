# Cache Algorithm Benchmark: LRU vs LFU under Zipfian Workloads

**Authors:** Azat Amir (3rd-year student, Narxoz University)
**Course:** Research Methods (Методы исследований)
**Repository:** https://github.com/Omor1M0ri/cache-algorithm-benchmark

## Research Question

Does the Least Frequently Used (LFU) eviction policy achieve a Cache Hit Rate that is
15–20 % higher (relative) than Least Recently Used (LRU) for a database-facing cache when
request popularity follows a Zipfian distribution?

- **H0:** Relative Hit Rate gain of LFU over LRU on a Zipfian workload (alpha = 1.0, cache = 1 % of keys) is < 15 %.
- **H1:** The gain is ≥ 15 % (expected 15–20 %).

## Overview

Two O(1) cache implementations (`src/cache.py`) sit in front of a database backend
(simulated or in-memory SQLite). A synthetic request stream is drawn from a Zipf law with
exponent alpha; both policies replay the *same* trace (paired design) over 10 random seeds.
The primary metric is Cache Hit Rate; the backend mean response time is a secondary
dependent variable. Full methodology: [`docs/methodology_card.md`](docs/methodology_card.md).

## Variables (summary)

| Type | Variables |
|---|---|
| Independent | eviction policy (LRU / LFU); cache size (100 / 500 / 1000 items); Zipf alpha (0.0, 0.6, 0.8, 1.0, 1.2) |
| Dependent | Cache Hit Rate (%) — primary; mean backend response time (ms) — secondary |
| Controlled | key space 10 000; 100 000 requests/run; 20 % warm-up; Python 3.12.7, pinned libs; fixed seeds |

## Planned Benchmarks

| ID | Workload | Cache sizes | Purpose |
|---|---|---|---|
| B0 | Uniform (alpha = 0.0) | 100, 500, 1000 | Negative control: no popularity skew, no expected LFU advantage |
| B1 | Zipf alpha = 0.6 | 100, 500, 1000 | Mild skew |
| B2 | Zipf alpha = 0.8 | 100, 500, 1000 | Moderate skew |
| B3 | Zipf alpha = 1.0 | 100, 500, 1000 | **Primary condition for H1** (cache = 100) |
| B4 | Zipf alpha = 1.2 | 100, 500, 1000 | Strong skew |

Each benchmark: 2 policies × 10 seeds.

## Repository Structure

```
cache-algorithm-benchmark/
├── README.md
├── LICENSE                  # MIT
├── Dockerfile               # python:3.12.7-slim + pinned requirements
├── requirements.txt         # exact version pins
├── .gitignore
├── configs/
│   ├── config.yaml          # full experiment parameters
│   └── sample.yaml          # smoke-test parameters
├── data/sample/sample_requests.csv   # 10-row sample trace
├── src/
│   ├── cache.py             # LRUCache, LFUCache (O(1))
│   ├── workload.py          # Zipf trace generator, CSV loader
│   ├── backend.py           # simulated / SQLite backends
│   ├── benchmark.py         # measurement loop, statistics, H1 check
│   ├── plot.py              # figures
│   └── main.py              # CLI entry point
├── scripts/run.sh           # wrapper: sample | full
├── tests/test_cache.py      # unit tests
├── notebooks/               # exploratory analysis (empty placeholder)
├── docs/methodology_card.md # variables matrix, metrics, baseline
└── results/full/            # summary.csv, raw_results.csv, figures
```

## System Requirements

- Python 3.12 (or Docker 24+)
- ~100 MB RAM; full run ≈ 30 s on a laptop CPU

## Quickstart

**Option A — Docker (2 commands):**
```bash
docker build -t cache-benchmark .
docker run --rm cache-benchmark          # smoke test on data/sample/
```

**Option B — local Python (3 commands):**
```bash
pip install -r requirements.txt
python -m pytest -q                      # unit tests
bash scripts/run.sh sample               # smoke test; writes results/sample/
```

Full experiment (Week 7 data collection):
```bash
bash scripts/run.sh full                 # writes results/full/ incl. figures
```

## Pilot Results (full grid, simulated backend)

Primary condition (alpha = 1.0, cache = 100): LRU 39.0 % vs LFU 50.0 % Hit Rate,
relative gain +28.1 % (95 % bootstrap CI 27.3–29.0 %). The gain depends strongly on
cache size and alpha; see `results/full/summary.csv`. The observed gain exceeds the
15–20 % band at small caches and falls inside/below it at larger caches.

## Citation

```
Amir, A. (2026). Cache Algorithm Benchmark: LRU vs LFU under Zipfian Workloads.
Narxoz University, Research Methods course project.
https://github.com/Omor1M0ri/cache-algorithm-benchmark
```

## License

MIT — see [LICENSE](LICENSE).
