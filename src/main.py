"""Entry point.  Usage:  python -m src.main --config configs/config.yaml"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

import yaml

from .benchmark import run_single, summarize, evaluate_hypothesis
from .workload import generate_trace, load_trace_from_csv, maybe_limit

log = logging.getLogger("main")


def setup_logging(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)s | %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(out_dir / "run.log", mode="w", encoding="utf-8"),
    ])


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="LRU vs LFU cache benchmark")
    ap.add_argument("--config", default="configs/config.yaml")
    ap.add_argument("--out", default=None, help="output dir (overrides config)")
    ap.add_argument("--plot", action="store_true", help="also save figures")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    out_dir = Path(args.out or cfg["output"]["dir"])
    setup_logging(out_dir)
    log.info("Config: %s", args.config)

    wl, ex = cfg["workload"], cfg["experiment"]
    backend_cfg = cfg["backend"]
    policies = [p.lower() for p in ex["policies"]]
    t_start = time.perf_counter()
    results = []

    if wl["source"] == "file":
        trace = maybe_limit(load_trace_from_csv(wl["path"]), wl.get("max_requests"))
        n_keys = int(trace.max()) + 1
        log.info("Loaded %d requests from %s (%d unique keys)", len(trace), wl["path"], n_keys)
        for size in ex["cache_sizes"]:
            for pol in policies:
                results.append(run_single(trace, pol, size, backend_cfg, n_keys,
                                          ex["warmup_fraction"]))
                r = results[-1]
                log.info("%s size=%d hit_rate=%.2f%% latency=%.4f ms", pol.upper(), size,
                         r.hit_rate, r.mean_latency_ms)
        summary, verdict = [], {"evaluated": False, "reason": "file workload (smoke test)"}
    else:
        n_keys = wl["n_keys"]
        for alpha in wl["zipf_alphas"]:
            for seed in ex["seeds"]:
                trace = generate_trace(n_keys, wl["n_requests"], alpha, seed)
                for size in ex["cache_sizes"]:
                    for pol in policies:
                        r = run_single(trace, pol, size, backend_cfg, n_keys,
                                       ex["warmup_fraction"], alpha=alpha, seed=seed)
                        results.append(r)
                        log.info("alpha=%.2f seed=%d size=%d %s hit=%.2f%% lat=%.4f ms",
                                 alpha, seed, size, pol.upper(), r.hit_rate, r.mean_latency_ms)
        summary = summarize(results)
        verdict = evaluate_hypothesis(summary, cfg)

    write_csv(out_dir / "raw_results.csv", [r.as_dict() for r in results])
    write_csv(out_dir / "summary.csv", summary)
    json.dump({"config": cfg, "hypothesis": verdict, "summary": summary},
              open(out_dir / "summary.json", "w", encoding="utf-8"), indent=2)
    if args.plot and summary:
        from .plot import plot_hit_rate_vs_alpha
        for p in plot_hit_rate_vs_alpha(summary, out_dir / "figures"):
            log.info("Saved figure %s", p)

    log.info("Hypothesis check: %s", json.dumps(verdict))
    log.info("Done in %.1fs. Results in %s", time.perf_counter() - t_start, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
