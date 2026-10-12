"""Figures for the report (matplotlib, headless backend)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_hit_rate_vs_alpha(summary: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = sorted({r["cache_size"] for r in summary})
    paths = []
    fig, axes = plt.subplots(1, len(sizes), figsize=(4.2 * len(sizes), 3.6), sharey=True, squeeze=False)
    for ax, size in zip(axes[0], sizes):
        rows = sorted((r for r in summary if r["cache_size"] == size), key=lambda r: r["alpha"])
        a = [r["alpha"] for r in rows]
        ax.errorbar(a, [r["lru_hit_rate_mean"] for r in rows], [r["lru_hit_rate_std"] for r in rows],
                    marker="o", capsize=3, label="LRU")
        ax.errorbar(a, [r["lfu_hit_rate_mean"] for r in rows], [r["lfu_hit_rate_std"] for r in rows],
                    marker="s", capsize=3, label="LFU")
        ax.set_title(f"cache size = {size}")
        ax.set_xlabel("Zipf exponent alpha")
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("Cache Hit Rate, %")
    axes[0][0].legend()
    fig.tight_layout()
    p = out_dir / "hit_rate_vs_alpha.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    paths.append(p)

    fig, ax = plt.subplots(figsize=(6, 3.8))
    for size in sizes:
        rows = sorted((r for r in summary if r["cache_size"] == size), key=lambda r: r["alpha"])
        ax.plot([r["alpha"] for r in rows], [r["delta_rel_pct_mean"] for r in rows], marker="o",
                label=f"size {size}")
    ax.axhspan(15, 20, color="green", alpha=0.12, label="H1 band (15-20%)")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("Zipf exponent alpha")
    ax.set_ylabel("LFU gain over LRU (relative, %)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = out_dir / "relative_gain.png"
    fig.savefig(p, dpi=160)
    plt.close(fig)
    paths.append(p)
    return paths
