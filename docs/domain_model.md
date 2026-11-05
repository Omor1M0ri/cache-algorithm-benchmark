# Domain Model — Cache Algorithm Benchmark (C4 Model, SE track)

The system under test is a **read-through cache in front of a database**. The benchmark
harness replays a synthetic Zipf request stream through two interchangeable cache
policies (LRU = baseline, LFU = proposed) and records metrics at clearly defined
measurement points (**M1–M5**, red nodes below).

## Level 1 — System Context

```mermaid
C4Context
    title System Context: LRU vs LFU cache benchmark
    Person(researcher, "Researcher", "Runs experiments, analyses results")
    System(bench, "Cache Benchmark Harness", "Replays Zipf workloads through LRU / LFU caches and logs raw measurements")
    SystemDb_Ext(db, "Database (SQLite in-memory)", "Source of truth: 10 000 rows, SELECT by primary key")
    System_Ext(git, "GitHub repository", "Code, raw sample log, processed CSV, figures")
    Rel(researcher, bench, "Configures & runs", "YAML config, CLI")
    Rel(bench, db, "Reads on cache miss", "SQL")
    Rel(researcher, git, "Publishes release")
```

## Level 2 — Containers

```mermaid
flowchart LR
    subgraph harness["Cache Benchmark Harness (Python 3.12, single process)"]
        direction LR
        cfg[/"configs/benchmark_raw.yaml<br/>experiment grid"/]
        wl["Workload Generator<br/>src/workload.py<br/>Zipf(α), seed-fixed trace"]
        runner["Benchmark Runner<br/>src/benchmark.py · run_logged()<br/>per-request loop"]
        cache["Cache Service<br/>src/cache.py<br/>LRUCache | LFUCache, O(1)"]
        backend["DB Backend Adapter<br/>src/backend.py<br/>SQLiteBackend"]
        logger["Raw Logger<br/>src/collect.py<br/>JSONL writer"]
    end
    db[("SQLite in-memory DB<br/>items(id, payload)")]
    raw[("data/raw/test_run.jsonl")]
    subgraph analysis["Analysis Pipeline"]
        proc["process_data.py<br/>warm-up filter, stats, bootstrap CI"]
        viz["visualize.py<br/>figures .pdf + .png"]
        nb["notebooks/01_data_analysis.ipynb"]
    end
    csv[("data/processed/metrics_summary.csv")]
    figs[("reports/figures/*")]

    cfg --> wl --> runner
    runner -- "get(key) / put(key,v)" --> cache
    runner -- "fetch(key) on miss" --> backend --> db
    runner --> logger --> raw
    raw --> proc --> csv
    nb --> proc
    nb --> viz --> figs
    proc --> viz

    m1(("M1 · t₀ / t₁<br/>request latency")):::meter
    m2(("M2 · hit / miss<br/>counter")):::meter
    m3(("M3 · payload check<br/>error counter")):::meter
    m4(("M4 · len(cache) ≤ C<br/>capacity guardrail")):::meter
    m5(("M5 · phase tag<br/>warm-up / benchmark")):::meter
    m1 -.- runner
    m2 -.- cache
    m3 -.- backend
    m4 -.- cache
    m5 -.- logger

    classDef meter fill:#fde0dc,stroke:#c0392b,stroke-width:2px,color:#000;
```

## Level 3 — Components of the measurement loop

```mermaid
flowchart TB
    subgraph runner["Benchmark Runner · run_logged()"]
        start(["for key in trace window (5 000 req)"]) --> t0["t₀ = perf_counter()"]:::meter
        t0 --> get{"cache.get(key)"}
        get -- hit --> nHit["hits += 1"]:::meter
        get -- miss --> fetch["backend.fetch(key)<br/>SELECT payload WHERE id=?"]
        fetch --> put["cache.put(key, value)<br/>evict: LRU = oldest access<br/>LFU = min freq, LRU tie-break"]
        nHit --> check
        put --> check{"value == payload-key ?"}:::meter
        check -- no / exception --> err["errors += 1"]:::meter
        check -- yes --> t1
        err --> t1["latency = perf_counter() − t₀"]:::meter
        t1 --> win{"window full?"}
        win -- no --> start
        win -- yes --> rec["emit JSONL record:<br/>phase, n, hits, errors, cache_len,<br/>lat_sum, p50/p95/p99, 100 latency samples"]:::meter
    end
    classDef meter fill:#fde0dc,stroke:#c0392b,stroke-width:2px,color:#000;
```

## Measurement points

| ID | Where | What is measured | Unit | Used for |
|---|---|---|---|---|
| M1 | Runner, around each request | wall-clock latency `perf_counter()` (lookup + DB fetch on miss) | µs | Fig. 1, Fig. 2, p50/p95/p99 |
| M2 | Cache `get()` result | hit / miss | count → % | Hit Rate (primary metric), Fig. 3–5 |
| M3 | Response validation | exception or wrong payload | count → % | **Guardrail:** error rate must be 0 % |
| M4 | Cache size after each window | `len(cache) ≤ capacity` | bool | **Guardrail:** capacity never exceeded |
| M5 | Logger | window start < 20 % of trace → `warmup` | tag | Warm-up filtering, Fig. 5 |

## Formal metric definitions

For policy $p \in \{\text{LRU}, \text{LFU}\}$, seed $s$, and the set $B$ of benchmark-phase requests:

$$HR_{p,s} = \frac{100}{|B|}\sum_{i \in B} \mathbb{1}[\text{hit}_i], \qquad
G_s = \frac{HR_{\text{LFU},s} - HR_{\text{LRU},s}}{HR_{\text{LRU},s}} \cdot 100\,\%$$

$$\bar T_{p,s} = \frac{1}{|B|}\sum_{i \in B} \left(t_{1,i} - t_{0,i}\right), \qquad
\text{CI}_{95}(\bar G) = \left[Q_{2.5}\!\left(\bar G^{*}\right),\; Q_{97.5}\!\left(\bar G^{*}\right)\right]$$

where $\bar G^{*}$ are 10 000 bootstrap means of $\{G_s\}_{s=0}^{9}$ (`seed = 42`).
**Decision rule:** reject $H_0$ iff the lower bound of $\text{CI}_{95}(\bar G) \ge 15\,\%$ at α = 1.0, C = 100.
