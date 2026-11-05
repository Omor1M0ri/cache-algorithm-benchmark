"""Week 7-8 data collection: write raw per-window measurements to JSONL.

Usage:
    python -m src.collect --config configs/benchmark_raw.yaml

Output (one JSON object per line):
    line 1        {"record": "meta", ...}   environment + config
    other lines   {"record": "window", ...} 5 000-request window of one run,
                  tagged phase = "warmup" | "benchmark"
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from .benchmark import run_logged
from .workload import generate_trace

log = logging.getLogger("collect")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect raw JSONL benchmark log")
    ap.add_argument("--config", default="configs/benchmark_raw.yaml")
    ap.add_argument("--out", default=None, help="JSONL path (overrides config)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                        stream=sys.stdout)

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    wl, ex, raw = cfg["workload"], cfg["experiment"], cfg["raw_log"]
    out = Path(args.out or raw["path"])
    out.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "record": "meta",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(), "numpy": np.__version__,
        "platform": platform.platform(), "processor": platform.processor() or "n/a",
        "config": cfg,
    }
    t_start = time.perf_counter()
    n_lines = 0
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        for alpha in wl["zipf_alphas"]:
            for seed in ex["seeds"]:
                trace = generate_trace(wl["n_keys"], wl["n_requests"], alpha, seed)
                for size in ex["cache_sizes"]:
                    # counterbalance execution order between policies (odd seeds: LFU first)
                    order = list(ex["policies"]) if seed % 2 == 0 else list(reversed(ex["policies"]))
                    for pol in order:
                        gc.collect()
                        recs = run_logged(trace, pol, size, cfg["backend"], wl["n_keys"],
                                          ex["warmup_fraction"], alpha=alpha, seed=seed,
                                          window=raw["window"],
                                          sample_per_window=raw["sample_per_window"])
                        for r in recs:
                            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
                        n_lines += len(recs)
                        bench = [r for r in recs if r["phase"] == "benchmark"]
                        hr = 100 * sum(r["hits"] for r in bench) / sum(r["n"] for r in bench)
                        log.info("alpha=%.1f seed=%d size=%4d %s hit=%.2f%% errors=%d",
                                 alpha, seed, size, pol.upper(), hr,
                                 sum(r["errors"] for r in recs))
    log.info("Wrote %d window records to %s in %.1fs", n_lines, out,
             time.perf_counter() - t_start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
