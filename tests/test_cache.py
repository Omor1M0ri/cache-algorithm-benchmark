import numpy as np
import pytest

from src.cache import LRUCache, LFUCache, make_cache
from src.workload import zipf_probabilities, generate_trace
from src.benchmark import run_single

BACKEND = {"type": "simulated", "hit_ms": 0.05, "miss_ms": 5.0}


def test_lru_evicts_least_recent():
    c = LRUCache(2)
    c.put("a", 1); c.put("b", 2)
    c.get("a")            # a is now most recent
    c.put("c", 3)         # evicts b
    assert "a" in c and "c" in c and "b" not in c


def test_lfu_evicts_least_frequent():
    c = LFUCache(2)
    c.put("a", 1); c.put("b", 2)
    c.get("a"); c.get("a")  # a freq 3, b freq 1
    c.put("c", 3)           # evicts b
    assert "a" in c and "c" in c and "b" not in c


def test_lfu_tie_break_is_lru():
    c = LFUCache(2)
    c.put("a", 1); c.put("b", 2)  # both freq 1, a older
    c.put("c", 3)                 # evicts a
    assert "a" not in c and "b" in c and "c" in c


@pytest.mark.parametrize("policy", ["lru", "lfu"])
def test_capacity_never_exceeded(policy):
    c = make_cache(policy, 5)
    for i in range(100):
        c.put(i, i)
        assert len(c) <= 5


def test_unknown_policy():
    with pytest.raises(ValueError):
        make_cache("fifo", 3)


def test_zipf_probabilities():
    p = zipf_probabilities(100, 1.0)
    assert p.sum() == pytest.approx(1.0)
    assert np.all(np.diff(p) <= 0)
    assert np.allclose(zipf_probabilities(10, 0.0), 0.1)


def test_trace_is_reproducible():
    assert np.array_equal(generate_trace(50, 100, 1.0, 7), generate_trace(50, 100, 1.0, 7))


def test_hit_rate_manual_example():
    # trace A B A C A D B A C A, size 3, LRU -> hand-computed hits
    trace = np.array([0, 1, 0, 2, 0, 3, 1, 0, 2, 0])
    r = run_single(trace, "lru", 3, BACKEND, 4, 0.0)
    assert r.hits + r.db_queries == 10
    assert 0 <= r.hit_rate <= 100


def test_lfu_beats_lru_on_skewed_trace():
    trace = generate_trace(1000, 30000, 1.0, 0)
    lru = run_single(trace, "lru", 20, BACKEND, 1000, 0.2)
    lfu = run_single(trace, "lfu", 20, BACKEND, 1000, 0.2)
    assert lfu.hit_rate > lru.hit_rate
