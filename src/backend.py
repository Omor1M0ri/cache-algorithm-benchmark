"""Database backends used to price a cache miss.

* SimulatedBackend - deterministic cost model (hit_ms / miss_ms from config).
* SQLiteBackend    - real in-memory SQLite lookups timed with perf_counter.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any


class SimulatedBackend:
    name = "simulated"

    def __init__(self, hit_ms: float, miss_ms: float, **_: Any) -> None:
        self.hit_ms = hit_ms
        self.miss_ms = miss_ms

    def fetch(self, key: int) -> tuple[int, float]:
        return key, self.miss_ms

    def hit_cost(self) -> float:
        return self.hit_ms


class SQLiteBackend:
    name = "sqlite"

    def __init__(self, n_keys: int, hit_ms: float = 0.001, **_: Any) -> None:
        self.hit_ms = hit_ms
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, payload TEXT)")
        self.conn.executemany(
            "INSERT INTO items VALUES (?, ?)", ((i, f"payload-{i}") for i in range(n_keys))
        )
        self.conn.commit()

    def fetch(self, key: int) -> tuple[str, float]:
        t0 = time.perf_counter()
        row = self.conn.execute("SELECT payload FROM items WHERE id = ?", (int(key),)).fetchone()
        return row[0], (time.perf_counter() - t0) * 1000.0

    def hit_cost(self) -> float:
        return self.hit_ms


def make_backend(cfg: dict, n_keys: int):
    kind = cfg.get("type", "simulated")
    if kind == "simulated":
        return SimulatedBackend(**{k: v for k, v in cfg.items() if k != "type"})
    if kind == "sqlite":
        return SQLiteBackend(n_keys=n_keys, hit_ms=cfg.get("hit_ms", 0.001))
    raise ValueError(f"Unknown backend type: {kind}")
