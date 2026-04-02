"""
Near-duplicate detection for news articles.

Goal:
- Fast, cheap candidate generation for "same story, rewritten" duplicates
- Deterministic, testable behavior (no ML dependency)

Approach:
- SimHash on word 3-gram shingles (64-bit)
- Lightweight banded bucket index for candidate lookup
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple


_WS_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = _NON_WORD_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def shingles(text: str, n: int = 3) -> List[str]:
    words = normalize_text(text).split(" ")
    words = [w for w in words if w]
    if len(words) < n:
        return [" ".join(words)] if words else []
    return [" ".join(words[i : i + n]) for i in range(0, len(words) - n + 1)]


def _hash64(value: str) -> int:
    # Stable 64-bit hash without external deps.
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def shingle_hashes(text: str, n: int = 3) -> Set[int]:
    """Return hashed shingle set for Jaccard comparisons."""
    return {_hash64(s) for s in shingles(text, n=n)}


def jaccard(a: Set[int], b: Set[int]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a) + len(b) - inter
    return float(inter) / float(union) if union else 0.0


def simhash64(text: str, shingle_n: int = 3) -> int:
    """
    Compute a 64-bit SimHash fingerprint.

    Returns:
        Unsigned 64-bit int in Python int space.
    """
    feats = shingles(text, n=shingle_n)
    if not feats:
        return 0

    # Standard SimHash: for each bit, add +1/-1 depending on feature hash bit.
    weights = [0] * 64
    for feat in feats:
        h = _hash64(feat)
        for bit in range(64):
            if (h >> bit) & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1

    out = 0
    for bit, w in enumerate(weights):
        if w > 0:
            out |= 1 << bit
    return out


def hamming_distance64(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


@dataclass(frozen=True)
class SimHashIndexConfig:
    bands: int = 4
    # Cap candidates per bucket to avoid pathological buckets for boilerplate content.
    max_bucket_size: int = 200


class SimHashIndex:
    def __init__(self, config: SimHashIndexConfig = SimHashIndexConfig()):
        if config.bands <= 0 or config.bands > 64:
            raise ValueError("bands must be in [1, 64]")
        self.config = config
        self._buckets: Dict[Tuple[int, int], List[Tuple[str, int]]] = {}

    def _band_keys(self, fp: int) -> List[Tuple[int, int]]:
        bands = self.config.bands
        band_size = 64 // bands
        if 64 % bands != 0:
            # Keep implementation simple and stable. Choose bands that divide 64.
            raise ValueError("bands must divide 64")
        keys: List[Tuple[int, int]] = []
        for band in range(bands):
            shift = band * band_size
            mask = (1 << band_size) - 1
            keys.append((band, (fp >> shift) & mask))
        return keys

    def add(self, doc_id: str, fp: int) -> None:
        for key in self._band_keys(fp):
            bucket = self._buckets.setdefault(key, [])
            if len(bucket) >= self.config.max_bucket_size:
                continue
            bucket.append((doc_id, fp))

    def candidates(self, fp: int) -> Iterable[Tuple[str, int]]:
        seen: set[str] = set()
        for key in self._band_keys(fp):
            for doc_id, other_fp in self._buckets.get(key, []):
                if doc_id in seen:
                    continue
                seen.add(doc_id)
                yield (doc_id, other_fp)
