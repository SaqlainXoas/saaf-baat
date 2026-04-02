from __future__ import annotations

from src.agents.dedup import SimHashIndex, SimHashIndexConfig, hamming_distance64, simhash64


def test_simhash_is_deterministic() -> None:
    text = "Pakistan inflation rises to 30 percent as food prices climb."
    assert simhash64(text) == simhash64(text)


def test_simhash_near_duplicates_have_small_hamming_distance() -> None:
    a = "Pakistan inflation rises to 30 percent as food prices climb."
    b = "Food prices climb as Pakistan inflation rises to 30%."
    c = "Cricket match postponed due to rain in Karachi."
    dist_ab = hamming_distance64(simhash64(a), simhash64(b))
    dist_ac = hamming_distance64(simhash64(a), simhash64(c))
    assert dist_ab < dist_ac


def test_index_returns_candidates_from_shared_buckets() -> None:
    idx = SimHashIndex(SimHashIndexConfig(bands=4))
    fp1 = simhash64("Rupee falls against dollar in early trading today.")
    fp2 = simhash64("Dollar gains against rupee in early trading.")
    idx.add("a", fp1)
    idx.add("b", fp2)

    cands = dict(idx.candidates(fp1))
    assert "a" in cands
