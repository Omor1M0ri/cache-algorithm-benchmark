"""Synthetic and file-based request workloads."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import numpy as np


def zipf_probabilities(n_keys: int, alpha: float) -> np.ndarray:
    """Finite Zipf: P(rank i) proportional to 1 / i**alpha, i = 1..n_keys.

    alpha = 0 gives the uniform distribution.
    """
    ranks = np.arange(1, n_keys + 1, dtype=np.float64)
    weights = ranks ** (-alpha)
    return weights / weights.sum()


def generate_trace(n_keys: int, n_requests: int, alpha: float, seed: int) -> np.ndarray:
    """Independent-reference-model trace of key ids drawn from a Zipf law."""
    rng = np.random.default_rng(seed)
    probs = zipf_probabilities(n_keys, alpha)
    return rng.choice(n_keys, size=n_requests, p=probs)


def load_trace_from_csv(path: str | Path, column: str = "key") -> np.ndarray:
    """Load a request trace (one key per row) from CSV."""
    keys = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            keys.append(row[column])
    # map arbitrary labels to integer ids, preserving first-seen order
    index: dict = {}
    return np.array([index.setdefault(k, len(index)) for k in keys], dtype=np.int64)


def maybe_limit(trace: np.ndarray, limit: Optional[int]) -> np.ndarray:
    return trace if not limit else trace[:limit]
