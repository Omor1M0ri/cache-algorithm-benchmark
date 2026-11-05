"""Publication figures for Task 3 (matplotlib + seaborn, headless).

Rules applied to every figure:
  * axis titles carry physical units (µs, %, requests);
  * uncertainty is always shown: shaded 95 % bootstrap CI bands or error bars;
  * colorblind-safe palette (seaborn "colorblind") AND a distinct marker +
    line style per series, so the figure stays readable in black-and-white print;
  * every figure is exported twice: vector .pdf (paper) and .png at 300 DPI (README).

CLI:  python -m src.visualize [raw.jsonl] [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from . import process_data as pdp

PALETTE = sns.color_palette("colorblind")
# identity of a series is encoded three ways: colour + marker + line style
POLICY_STYLE = {
    "lru": dict(color=PALETTE[0], marker="o", linestyle="--", label="LRU (baseline)"),
    "lfu": dict(color=PALETTE[1], marker="s", linestyle="-", label="LFU (proposed)"),
}
SIZE_STYLE = {
    100: dict(color=PALETTE[0], marker="o", linestyle="-"),
    500: dict(color=PALETTE[1], marker="s", linestyle="--"),
    1000: dict(color=PALETTE[2], marker="^", linestyle=":"),
}
HATCH = {"lru": "", "lfu": "///"}
DPI = 300


def set_style() -> None:
    sns.set_theme(style="whitegrid", context="paper", palette=PALETTE)
    plt.rcParams.update({
        "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9, "legend.fontsize": 8,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "lines.linewidth": 1.6,
        "lines.markersize": 5, "grid.alpha": 0.35, "pdf.fonttype": 42,
        "savefig.bbox": "tight", "axes.spines.top": False, "axes.spines.right": False,
    })


def save(fig: plt.Figure, out_dir: Path, name: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.pdf", out_dir / f"{name}.png"]
    fig.savefig(paths[0])
    fig.savefig(paths[1], dpi=DPI)
    plt.close(fig)
    return paths


def _ci_line(ax, x, mean, lo, hi, style: dict) -> None:
    ax.plot(x, mean, **style)
    ax.fill_between(x, lo, hi, color=style["color"], alpha=0.2, linewidth=0)


def _by_size_panels(summary: pd.DataFrame, metric: str, ylabel: str, log: bool = False):
    sizes = sorted(summary.cache_size.unique())
    fig, axes = plt.subplots(1, len(sizes), figsize=(7.2, 2.7), sharey=True)
    for ax, size in zip(axes, sizes):
        for pol, st in POLICY_STYLE.items():
            d = summary[(summary.cache_size == size) & (summary.policy == pol)].sort_values("alpha")
            _ci_line(ax, d.alpha, d[f"{metric}_mean"], d[f"{metric}_ci95_lo"],
                     d[f"{metric}_ci95_hi"], st)
        ax.set_title(f"Cache = {size} items ({size // 100} % of keys)")
        ax.set_xticks(sorted(summary.alpha.unique()))
        if log:
            ax.set_yscale("log")
    axes[0].set_ylabel(ylabel)
    axes[0].legend(loc="best", frameon=True)
    fig.supxlabel("Workload skew, Zipf α (dimensionless)", fontsize=9)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- figures
def fig1_latency_vs_load(summary: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Mean per-request latency vs workload skew, 95 % bootstrap CI bands."""
    fig = _by_size_panels(summary, "lat_mean_us", "Mean request latency (µs)")
    fig.suptitle("Fig. 1. Measured latency vs workload (SQLite in-memory backend), "
                 "shaded = 95 % bootstrap CI over 10 seeds", y=1.03, fontsize=9)
    return save(fig, out_dir, "fig1_latency_vs_load")


def fig2_distribution_boxplot(samples: pd.DataFrame, out_dir: Path, alpha: float = 1.0) -> list[Path]:
    """Per-request latency distribution at the primary condition, log scale."""
    d = samples[samples.alpha == alpha].copy()
    d["Method"] = d.policy.map(lambda p: POLICY_STYLE[p]["label"])
    order = [POLICY_STYLE[p]["label"] for p in ["lru", "lfu"]]
    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    sns.boxplot(data=d, x="cache_size", y="lat_us", hue="Method", hue_order=order,
                palette=[POLICY_STYLE["lru"]["color"], POLICY_STYLE["lfu"]["color"]],
                whis=(1, 99), showfliers=True, width=0.7, linewidth=0.9, ax=ax,
                flierprops=dict(marker=".", markersize=1.5, alpha=0.3),
                medianprops=dict(color="black", linewidth=1.3))
    # hatch LFU boxes so the two methods differ without colour
    n_sizes = d.cache_size.nunique()
    for i, patch in enumerate(ax.patches[: 2 * n_sizes]):
        patch.set_hatch(HATCH["lru"] if i < n_sizes else HATCH["lfu"])
        patch.set_edgecolor("black")
    handles, labels = ax.get_legend_handles_labels()
    for h, lab in zip(handles, labels):
        h.set_hatch(HATCH["lfu"] if "LFU" in lab else HATCH["lru"])
        h.set_edgecolor("black")
    ax.legend(handles, labels, title=None, loc="upper right")
    ax.set_yscale("log")
    ax.set_xlabel("Cache size (items)")
    ax.set_ylabel("Per-request latency (µs, log scale)")
    ax.set_title(f"Fig. 2. Latency distribution at Zipf α = {alpha:g} "
                 "(box = p25–p75, whiskers = p1–p99)")
    fig.tight_layout()
    return save(fig, out_dir, "fig2_distribution_boxplot")


def fig3_hit_rate_vs_alpha(summary: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Primary metric: Cache Hit Rate vs skew (log y: values span 1 %-90 %)."""
    fig = _by_size_panels(summary, "hit_rate", "Cache Hit Rate (%, log scale)", log=True)
    fig.suptitle("Fig. 3. Cache Hit Rate vs workload skew; 95 % bootstrap CI bands are shaded "
                 "(narrower than the markers: SD ≤ 0.5 pp over 10 seeds)",
                 y=1.03, fontsize=9)
    return save(fig, out_dir, "fig3_hit_rate_vs_alpha")


def fig4_relative_gain(gains: pd.DataFrame, out_dir: Path,
                       band: tuple[float, float] = (15.0, 20.0)) -> list[Path]:
    """Paired relative Hit Rate gain of LFU over LRU with 95 % CI error bars."""
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    ax.axhspan(*band, color="0.6", alpha=0.25, hatch="..", linewidth=0,
               label=f"H1 band ({band[0]:g}–{band[1]:g} %)")
    ax.axhline(0, color="black", linewidth=0.8)
    offsets = {100: -0.015, 500: 0.0, 1000: 0.015}
    for size, st in SIZE_STYLE.items():
        d = gains[gains.cache_size == size].sort_values("alpha")
        yerr = np.vstack([d.rel_gain_pct - d.rel_gain_ci95_lo, d.rel_gain_ci95_hi - d.rel_gain_pct])
        ax.errorbar(d.alpha + offsets[size], d.rel_gain_pct, yerr=yerr, capsize=3,
                    label=f"cache = {size} items", **st)
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xticks(sorted(gains.alpha.unique()))
    ax.set_xlabel("Workload skew, Zipf α (dimensionless)")
    ax.set_ylabel("LFU gain over LRU in Hit Rate (%)\nsymlog scale")
    ax.set_title("Fig. 4. Paired relative gain, error bars = 95 % bootstrap CI")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=7, frameon=False)
    fig.tight_layout()
    return save(fig, out_dir, "fig4_relative_gain")


def fig5_warmup(profile: pd.DataFrame, out_dir: Path, alpha: float = 1.0,
                warmup_requests: int = 20_000) -> list[Path]:
    """Hit rate per 5 000-request window: shows why the first 20 % are discarded."""
    sizes = sorted(profile.cache_size.unique())
    fig, axes = plt.subplots(1, len(sizes), figsize=(7.2, 2.6), sharey=True)
    for ax, size in zip(axes, sizes):
        for pol, st in POLICY_STYLE.items():
            d = profile[(profile.alpha == alpha) & (profile.cache_size == size)
                        & (profile.policy == pol)].sort_values("req_start")
            x = (d.req_start + 2500) / 1000
            sd = d.hit_rate_sd.fillna(0)
            # 95 % CI of the mean over seeds (normal approx., n = 10)
            half = 1.96 * sd / np.sqrt(d.n_seeds)
            _ci_line(ax, x, d.hit_rate_mean, d.hit_rate_mean - half, d.hit_rate_mean + half,
                     {**st, "markersize": 3.5})
        ax.axvspan(0, warmup_requests / 1000, color="0.5", alpha=0.15, hatch="//", linewidth=0,
                   label="warm-up, first 20 % (dropped)")
        ax.axvline(warmup_requests / 1000, color="black", linewidth=0.8, linestyle="-.")
        ax.set_title(f"Cache = {size} items")
    axes[0].set_ylabel("Hit Rate per window (%)")
    fig.supxlabel("Requests processed (×1000)", fontsize=9)
    axes[0].legend(loc="upper right", fontsize=7)
    fig.suptitle(f"Fig. 5. Warm-up phase at Zipf α = {alpha:g}, shaded = 95 % CI over seeds",
                 y=1.03, fontsize=9)
    fig.tight_layout()
    return save(fig, out_dir, "fig5_warmup_phase")


def make_all(raw: Path, out_dir: Path) -> list[Path]:
    set_style()
    _, windows = pdp.load_raw(raw)
    bench = pdp.filter_warmup(windows)
    runs = pdp.per_run_metrics(bench)
    samples = pdp.latency_samples(bench)
    summary = pdp.aggregate(runs, samples)
    gains = pdp.paired_gains(runs)
    paths = []
    paths += fig1_latency_vs_load(summary, out_dir)
    paths += fig2_distribution_boxplot(samples, out_dir)
    paths += fig3_hit_rate_vs_alpha(summary, out_dir)
    paths += fig4_relative_gain(gains, out_dir)
    paths += fig5_warmup(pdp.warmup_profile(windows), out_dir)
    return paths


if __name__ == "__main__":
    a = sys.argv[1:]
    for p in make_all(Path(a[0]) if a else Path("data/raw/test_run.jsonl"),
                      Path(a[1]) if len(a) > 1 else Path("reports/figures")):
        print("saved", p)
