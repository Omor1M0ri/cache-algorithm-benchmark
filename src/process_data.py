"""Cleaning and statistical aggregation of the raw JSONL benchmark log.

Pipeline (used by notebooks/01_data_analysis.ipynb):

    meta, windows = load_raw("data/raw/test_run.jsonl")
    bench         = filter_warmup(windows)            # drop cold-cache windows
    runs          = per_run_metrics(bench)            # one row per (alpha, size, policy, seed)
    samples       = latency_samples(bench)            # long table of per-request latencies
    summary       = aggregate(runs, samples)          # -> data/processed/metrics_summary.csv
    gains         = paired_gains(runs)                # LFU vs LRU, paired by seed
    guardrails    = check_guardrails(windows)

CLI:  python -m src.process_data [raw.jsonl] [out.csv]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd

SEED = 42
KEYS = ["alpha", "cache_size", "policy"]
POLICY_LABEL = {"lru": "LRU (baseline)", "lfu": "LFU (proposed)"}


# --------------------------------------------------------------------------- ingestion
def load_raw(path: str | Path) -> tuple[dict, pd.DataFrame]:
    """Read the JSONL log. Returns (meta record, DataFrame of window records)."""
    meta, rows = {}, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("record") == "meta":
                meta = rec
            elif rec.get("record") == "window":
                rows.append(rec)
    df = pd.DataFrame(rows)
    df["alpha"] = df["alpha"].astype(float).round(2)
    return meta, df


def filter_warmup(windows: pd.DataFrame) -> pd.DataFrame:
    """Keep only steady-state windows (phase == 'benchmark')."""
    return windows[windows["phase"] == "benchmark"].copy()


def warmup_profile(windows: pd.DataFrame) -> pd.DataFrame:
    """Hit rate per window index, averaged over seeds (for the warm-up figure)."""
    w = windows.assign(hit_rate=100.0 * windows["hits"] / windows["n"])
    return (w.groupby(KEYS + ["window", "req_start", "phase"], as_index=False)
             .agg(hit_rate_mean=("hit_rate", "mean"), hit_rate_sd=("hit_rate", "std"),
                  n_seeds=("seed", "nunique")))


# --------------------------------------------------------------------------- per run
def per_run_metrics(bench: pd.DataFrame) -> pd.DataFrame:
    """Exact per-run metrics from benchmark windows (latencies converted to µs)."""
    def _agg(g: pd.DataFrame) -> pd.Series:
        n = g["n"].sum()
        lat = np.concatenate(g["lat_sample_ms"].to_numpy()) * 1000.0  # ms -> µs
        p50, p95, p99 = np.percentile(lat, [50, 95, 99])
        return pd.Series({
            "requests": n,
            "hit_rate": 100.0 * g["hits"].sum() / n,
            "lat_mean_us": 1000.0 * g["lat_sum_ms"].sum() / n,   # exact (all requests)
            "lat_p50_us": p50, "lat_p95_us": p95, "lat_p99_us": p99,  # from samples
            "throughput_rps": n / g["wall_s"].sum(),
            "error_rate": 100.0 * g["errors"].sum() / n,
            "capacity_ok": bool(g["capacity_ok"].all()),
        })
    out = (bench.groupby(KEYS + ["seed"]).apply(_agg, include_groups=False)
                .reset_index())
    out["requests"] = out["requests"].astype(int)
    return out


def latency_samples(bench: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per sampled request latency (µs)."""
    s = bench[KEYS + ["seed", "lat_sample_ms"]].explode("lat_sample_ms")
    s["lat_us"] = s.pop("lat_sample_ms").astype(float) * 1000.0
    return s.reset_index(drop=True)


# --------------------------------------------------------------------------- statistics
def bootstrap_ci(values: Iterable[float], stat: Callable = np.mean, n_boot: int = 10_000,
                 level: float = 0.95, seed: int = SEED) -> tuple[float, float]:
    """Percentile bootstrap CI of `stat` (resampling seeds with replacement)."""
    arr = np.asarray(list(values), dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        v = float(arr[0]) if len(arr) else float("nan")
        return v, v
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    boots = stat(arr[idx], axis=1)
    lo, hi = np.percentile(boots, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def aggregate(runs: pd.DataFrame, samples: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """One row per (alpha, cache_size, policy): Mean±SD, 95 % CI, quantiles."""
    rows = []
    for key, g in runs.groupby(KEYS):
        s = samples
        lat = s[(s.alpha == key[0]) & (s.cache_size == key[1]) & (s.policy == key[2])]["lat_us"]
        q25, q50, q75, q95, q99 = np.percentile(lat, [25, 50, 75, 95, 99])
        row = dict(zip(KEYS, key))
        row["n_seeds"] = len(g)
        for m in ["hit_rate", "lat_mean_us", "lat_p95_us", "lat_p99_us", "throughput_rps"]:
            lo, hi = bootstrap_ci(g[m], seed=seed)
            row[f"{m}_mean"] = g[m].mean()
            row[f"{m}_sd"] = g[m].std(ddof=1)
            row[f"{m}_ci95_lo"], row[f"{m}_ci95_hi"] = lo, hi
        row.update({"lat_pooled_p25_us": q25, "lat_pooled_median_us": q50,
                    "lat_pooled_p75_us": q75, "lat_pooled_p95_us": q95,
                    "lat_pooled_p99_us": q99, "n_latency_samples": len(lat),
                    "error_rate_max": g["error_rate"].max(),
                    "capacity_ok": bool(g["capacity_ok"].all())})
        rows.append(row)
    return pd.DataFrame(rows)


def paired_gains(runs: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """LFU vs LRU on the same trace (paired by seed): relative hit-rate gain and Δlatency."""
    wide = runs.pivot_table(index=["alpha", "cache_size", "seed"], columns="policy",
                            values=["hit_rate", "lat_mean_us", "lat_p99_us"])
    rows = []
    for (alpha, size), g in wide.groupby(level=["alpha", "cache_size"]):
        hr_lru, hr_lfu = g["hit_rate"]["lru"], g["hit_rate"]["lfu"]
        rel = ((hr_lfu - hr_lru) / hr_lru * 100.0).to_numpy()
        dlat = ((g["lat_mean_us"]["lfu"] - g["lat_mean_us"]["lru"])
                / g["lat_mean_us"]["lru"] * 100.0).to_numpy()
        lo, hi = bootstrap_ci(rel, seed=seed)
        dlo, dhi = bootstrap_ci(dlat, seed=seed)
        rows.append({"alpha": alpha, "cache_size": size, "n_pairs": len(rel),
                     "delta_hit_pp": float((hr_lfu - hr_lru).mean()),
                     "rel_gain_pct": float(rel.mean()), "rel_gain_ci95_lo": lo,
                     "rel_gain_ci95_hi": hi,
                     "rel_latency_change_pct": float(dlat.mean()),
                     "rel_latency_ci95_lo": dlo, "rel_latency_ci95_hi": dhi,
                     "lfu_wins_seeds": int((rel > 0).sum())})
    return pd.DataFrame(rows)


def evaluate_h1(gains: pd.DataFrame, alpha: float = 1.0, cache_size: int = 100,
                threshold: float = 15.0) -> dict:
    """Reject H0 iff the lower 95 % CI bound of the relative gain is >= threshold."""
    r = gains[(gains.alpha == alpha) & (gains.cache_size == cache_size)].iloc[0]
    return {"alpha": alpha, "cache_size": cache_size, "rel_gain_pct": r.rel_gain_pct,
            "ci95": (r.rel_gain_ci95_lo, r.rel_gain_ci95_hi), "threshold_pct": threshold,
            "H0_rejected": bool(r.rel_gain_ci95_lo >= threshold)}


def check_guardrails(windows: pd.DataFrame) -> dict:
    """Guardrail metrics over the whole log (incl. warm-up): must all pass."""
    errors = int(windows["errors"].sum())
    return {"total_requests": int(windows["n"].sum()), "errors": errors,
            "error_rate_pct": 100.0 * errors / windows["n"].sum(),
            "capacity_violations": int((~windows["capacity_ok"]).sum()),
            "passed": errors == 0 and bool(windows["capacity_ok"].all())}


# --------------------------------------------------------------------------- tables
def fmt_mean_sd(m: float, sd: float, nd: int = 2) -> str:
    return f"{m:.{nd}f} ± {sd:.{nd}f}"


def results_table(summary: pd.DataFrame, gains: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Baseline (LRU) vs Proposed (LFU) table for one alpha, for the README."""
    rows = []
    for size in sorted(summary.cache_size.unique()):
        g = gains[(gains.alpha == alpha) & (gains.cache_size == size)].iloc[0]
        for pol in ["lru", "lfu"]:
            r = summary[(summary.alpha == alpha) & (summary.cache_size == size)
                        & (summary.policy == pol)].iloc[0]
            rows.append({
                "Cache size": size, "Method": POLICY_LABEL[pol],
                "Hit Rate, % (Mean ± SD)": fmt_mean_sd(r.hit_rate_mean, r.hit_rate_sd),
                "Latency, µs Median (p25–p75)":
                    f"{r.lat_pooled_median_us:.2f} ({r.lat_pooled_p25_us:.2f}–{r.lat_pooled_p75_us:.2f})",
                "p95, µs": f"{r.lat_pooled_p95_us:.2f}", "p99, µs": f"{r.lat_pooled_p99_us:.2f}",
                "Mean latency, µs [95% CI]":
                    f"{r.lat_mean_us_mean:.2f} [{r.lat_mean_us_ci95_lo:.2f}, {r.lat_mean_us_ci95_hi:.2f}]",
                "Rel. HR gain, % [95% CI]": "—" if pol == "lru" else
                    f"{g.rel_gain_pct:+.1f} [{g.rel_gain_ci95_lo:+.1f}, {g.rel_gain_ci95_hi:+.1f}]",
                "Errors, %": f"{r.error_rate_max:.2f}",
            })
    return pd.DataFrame(rows)


def to_markdown(df: pd.DataFrame) -> str:
    """Minimal GitHub-flavoured Markdown table (no `tabulate` dependency)."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def break_even(summary: pd.DataFrame, db_extra_ms: float = 5.0) -> pd.DataFrame:
    """Measured in-process cost + modelled remote-DB penalty per miss.

    E[T_p] = T_measured,p + (1 - HR_p) * t_db,   t_db = extra round-trip of a remote DB.
    Break-even t_db* = (T_LFU - T_LRU) / (HR_LFU - HR_LRU): LFU is faster for t_db > t_db*.
    """
    rows = []
    for (alpha, size), g in summary.groupby(["alpha", "cache_size"]):
        lru = g[g.policy == "lru"].iloc[0]
        lfu = g[g.policy == "lfu"].iloc[0]
        d_hr = (lfu.hit_rate_mean - lru.hit_rate_mean) / 100.0
        d_t = lfu.lat_mean_us_mean - lru.lat_mean_us_mean
        t_lru = lru.lat_mean_us_mean + (1 - lru.hit_rate_mean / 100) * db_extra_ms * 1000
        t_lfu = lfu.lat_mean_us_mean + (1 - lfu.hit_rate_mean / 100) * db_extra_ms * 1000
        rows.append({"alpha": alpha, "cache_size": size,
                     "measured_overhead_lfu_minus_lru_us": d_t,
                     "breakeven_db_penalty_us": d_t / d_hr if d_hr > 0 else float("inf"),
                     f"modelled_lru_ms@{db_extra_ms:g}ms": t_lru / 1000,
                     f"modelled_lfu_ms@{db_extra_ms:g}ms": t_lfu / 1000,
                     "modelled_latency_change_pct": (t_lfu - t_lru) / t_lru * 100})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    raw = Path(argv[0]) if argv else Path("data/raw/test_run.jsonl")
    out = Path(argv[1]) if len(argv) > 1 else Path("data/processed/metrics_summary.csv")
    _, windows = load_raw(raw)
    bench = filter_warmup(windows)
    runs = per_run_metrics(bench)
    summary = aggregate(runs, latency_samples(bench))
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False, float_format="%.6g")
    paired_gains(runs).to_csv(out.with_name("paired_gains.csv"), index=False, float_format="%.6g")
    print(f"Wrote {out} ({len(summary)} rows); guardrails: {check_guardrails(windows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
