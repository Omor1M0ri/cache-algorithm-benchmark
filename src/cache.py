"""Cache eviction policies: LRU and LFU, both with O(1) get/put.

Both caches share the same interface so they can be swapped in the benchmark:
    get(key) -> value or None
    put(key, value) -> None
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict, defaultdict
from typing import Any, Hashable, Optional


class BaseCache(ABC):
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity

    @abstractmethod
    def get(self, key: Hashable) -> Optional[Any]: ...

    @abstractmethod
    def put(self, key: Hashable, value: Any) -> None: ...

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __contains__(self, key: Hashable) -> bool: ...


class LRUCache(BaseCache):
    """Least Recently Used: evicts the entry that was accessed longest ago."""

    def __init__(self, capacity: int) -> None:
        super().__init__(capacity)
        self._data: "OrderedDict[Hashable, Any]" = OrderedDict()

    def get(self, key):
        if key not in self._data:
            return None
        self._data.move_to_end(key)  # mark as most recently used
        return self._data[key]

    def put(self, key, value) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        elif len(self._data) >= self.capacity:
            self._data.popitem(last=False)  # evict least recently used
        self._data[key] = value

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key) -> bool:
        return key in self._data


class LFUCache(BaseCache):
    """Least Frequently Used (in-cache frequency counters).

    Evicts the entry with the lowest access count; ties are broken by
    least-recent use. Counters are reset when an entry is evicted.
    Implementation: frequency -> OrderedDict(keys) buckets + min_freq pointer,
    giving O(1) get/put.
    """

    def __init__(self, capacity: int) -> None:
        super().__init__(capacity)
        self._values: dict = {}
        self._freq: dict = {}
        self._buckets: "defaultdict[int, OrderedDict]" = defaultdict(OrderedDict)
        self._min_freq = 0

    def _touch(self, key) -> None:
        f = self._freq[key]
        del self._buckets[f][key]
        if not self._buckets[f]:
            del self._buckets[f]
            if self._min_freq == f:
                self._min_freq = f + 1
        self._freq[key] = f + 1
        self._buckets[f + 1][key] = None

    def get(self, key):
        if key not in self._values:
            return None
        self._touch(key)
        return self._values[key]

    def put(self, key, value) -> None:
        if key in self._values:
            self._values[key] = value
            self._touch(key)
            return
        if len(self._values) >= self.capacity:
            bucket = self._buckets[self._min_freq]
            victim, _ = bucket.popitem(last=False)  # LFU, then LRU tie-break
            if not bucket:
                del self._buckets[self._min_freq]
            del self._values[victim]
            del self._freq[victim]
        self._values[key] = value
        self._freq[key] = 1
        self._buckets[1][key] = None
        self._min_freq = 1

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, key) -> bool:
        return key in self._values


POLICIES = {"lru": LRUCache, "lfu": LFUCache}


def make_cache(policy: str, capacity: int) -> BaseCache:
    try:
        return POLICIES[policy.lower()](capacity)
    except KeyError as exc:
        raise ValueError(f"Unknown policy '{policy}'. Choose from {list(POLICIES)}") from exc
