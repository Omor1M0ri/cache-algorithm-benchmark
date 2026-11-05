"""Core measurement loop and statistics."""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np

from .cache import make_cache
from .backend import make_backend

log = logging.getLogger("benchmark")


@dataclass
class RunResult:
    policy: str
    cache_size: int
    alpha: float
    seed: int
    requests: int
    hits: int
    hit_rate: float          # percent, measured after warm-up
    mean_latency_ms: float   # mean backend response time per request
    db_queries: int          # number of cache misses after warm-up (DB queries)

    def as_dict(self) -> dict:
        return asdict(self)


def run_single(trace: np.ndarray, policy: str, cache_size: int, backend_cfg: dict,
               n_keys: int, warmup_fraction: float, alpha: float = float("nan"),
               seed: int = -1) -> RunResult:
    cache = make_cache(policy, cache_size)
    backend = make_backend(backend_cfg, n_keys)
    hit_cost = backend.hit_cost()
    warmup = int(len(trace) * warmup_fraction)

    hits = misses = 0
    total_ms = 0.0
    for i, key in enumerate(trace.tolist()):
        measured = i >= warmup
        if cache.get(key) is not None:
            if measured:
                hits += 1
                total_ms += hit_cost
        else:
            value, cost = backend.fetch(key)
            cache.put(key, value)
            if measured:
                misses += 1
                total_ms += cost + hit_cost  # lookup + DB round trip
    n = hits + misses
    return RunResult(
        policy=policy, cache_size=cache_size, alpha=alpha, seed=seed, requests=n,
        hits=hits, hit_rate=100.0 * hits / n if n else 0.0,
        mean_latency_ms=total_ms / n if n else 0.0, db_queries=misses,
    )


def bootstrap_ci(values: Iterable[float], n_boot: int = 5000, level: float = 0.95,
                 seed: int = 0) -> tuple[float, float]:
    arr = np.asarray(list(values), dtype=float)
    if len(arr) < 2:
        v = float(arr[0]) if len(arr) else float("nan")
        return v, v
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def summarize(results: list[RunResult]) -> list[dict]:
    """Paired comparison LFU vs LRU per (cache_size, alpha); same trace per seed."""
    groups: dict = {}
    for r in results:
        groups.setdefault((r.alpha, r.cache_size), {}).setdefault(r.policy, {})[r.seed] = r
    rows = []
    for (alpha, size), by_policy in sorted(groups.items()):
        if "lru" not in by_policy or "lfu" not in by_policy:
            continue
        seeds = sorted(set(by_policy["lru"]) & set(by_policy["lfu"]))
        lru = np.array([by_policy["lru"][s].hit_rate for s in seeds])
        lfu = np.array([by_policy["lfu"][s].hit_rate for s in seeds])
        lat_lru = np.array([by_policy["lru"][s].mean_latency_ms for s in seeds])
        lat_lfu = np.array([by_policy["lfu"][s].mean_latency_ms for s in seeds])
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = (lfu - lru) / lru * 100.0
        lo, hi = bootstrap_ci(rel)
        rows.append({
            "alpha": alpha, "cache_size": size, "n_seeds": len(seeds),
            "lru_hit_rate_mean": float(lru.mean()), "lru_hit_rate_std": float(lru.std(ddof=1)) if len(seeds) > 1 else 0.0,
            "lfu_hit_rate_mean": float(lfu.mean()), "lfu_hit_rate_std": float(lfu.std(ddof=1)) if len(seeds) > 1 else 0.0,
            "delta_pp_mean": float((lfu - lru).mean()),
            "delta_rel_pct_mean": float(np.nanmean(rel)),
            "delta_rel_pct_ci95_lo": lo, "delta_rel_pct_ci95_hi": hi,
            "lru_latency_ms_mean": float(lat_lru.mean()),
            "lfu_latency_ms_mean": float(lat_lfu.mean()),
        })
    return rows


def evaluate_hypothesis(summary: list[dict], cfg: dict) -> dict:
    """H1: relative Hit Rate gain of LFU over LRU lies in/above [min, max] % at the primary condition."""
    h = cfg["hypothesis"]
    primary = [r for r in summary
               if abs(r["alpha"] - h["primary_alpha"]) < 1e-9 and r["cache_size"] == h["primary_cache_size"]]
    if not primary:
        return {"evaluated": False, "reason": "primary condition not in grid"}
    r = primary[0]
    lo_ci = r["delta_rel_pct_ci95_lo"]
    return {
        "evaluated": True,
        "primary_alpha": h["primary_alpha"],
        "primary_cache_size": h["primary_cache_size"],
        "observed_rel_gain_pct": r["delta_rel_pct_mean"],
        "ci95": [r["delta_rel_pct_ci95_lo"], r["delta_rel_pct_ci95_hi"]],
        "threshold_min_pct": h["min_rel_gain_pct"],
        "H0_rejected": bool(lo_ci >= h["min_rel_gain_pct"]),
        "note": "H0 is rejected only if the lower 95% CI bound is >= the minimum gain threshold.",
    }


# ---------------------------------------------------------------------------
# Task 3: raw per-window logging with real wall-clock timing
# ---------------------------------------------------------------------------
import time as _time

POLICY_IDX = {"lru": 0, "lfu": 1}


def run_logged(trace: np.ndarray, policy: str, cache_size: int, backend_cfg: dict,
               n_keys: int, warmup_fraction: float, alpha: float, seed: int,
               window: int = 5000, sample_per_window: int = 100) -> list[dict]:
    """Replay `trace` and return one raw record per window of `window` requests.

    Every request is timed with time.perf_counter() (cache lookup + DB fetch on a
    miss). Windows that start before ``warmup_fraction * len(trace)`` are tagged
    ``phase="warmup"`` (cold cache) and must be dropped during analysis.

    Each response is validated against the expected payload; an exception or a
    wrong value counts as an error (guardrail metric, must stay at 0).
    """
    cache = make_cache(policy, cache_size)
    backend = make_backend(backend_cfg, n_keys)
    warmup = int(len(trace) * warmup_fraction)
    run_id = f"a{alpha:.1f}_c{cache_size}_{policy}_s{seed}"
    rng = np.random.default_rng([seed, int(round(alpha * 10)), cache_size, POLICY_IDX.get(policy, 9)])
    perf = _time.perf_counter
    keys = trace.tolist()
    records: list[dict] = []

    for w_idx, start in enumerate(range(0, len(keys), window)):
        chunk = keys[start:start + window]
        lat = np.empty(len(chunk))
        hits = errors = 0
        w0 = perf()
        for j, key in enumerate(chunk):
            t0 = perf()
            try:
                value = cache.get(key)
                if value is not None:
                    hits += 1
                else:
                    value, _ = backend.fetch(key)
                    cache.put(key, value)
                ok = value == f"payload-{key}"
            except Exception:  # noqa: BLE001 - any failure is a guardrail error
                ok = False
            lat[j] = (perf() - t0) * 1000.0
            if not ok:
                errors += 1
        wall = perf() - w0
        sample = rng.choice(lat, size=min(sample_per_window, len(lat)), replace=False)
        p50, p95, p99 = np.percentile(lat, [50, 95, 99])
        records.append({
            "record": "window", "run_id": run_id, "policy": policy,
            "cache_size": cache_size, "alpha": alpha, "seed": seed,
            "window": w_idx, "req_start": start,
            "phase": "warmup" if start < warmup else "benchmark",
            "n": len(chunk), "hits": hits, "errors": errors,
            "cache_len": len(cache), "capacity_ok": len(cache) <= cache_size,
            "lat_sum_ms": round(float(lat.sum()), 6),
            "lat_p50_ms": round(float(p50), 6), "lat_p95_ms": round(float(p95), 6),
            "lat_p99_ms": round(float(p99), 6), "lat_max_ms": round(float(lat.max()), 6),
            "wall_s": round(wall, 6),
            "lat_sample_ms": [round(float(x), 5) for x in sample],
        })
    return records
