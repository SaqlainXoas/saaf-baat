"""Text splitting shared by the snippet builder and the analysis validators."""

from __future__ import annotations

import re
from typing import List

# A period is not always a full stop. This corpus is full of "Sept. 16",
# "Dr. Uzma Khan", "Rs. 30m" and "No. 4", and a naive `(?<=[.!?])\s+` split
# turns each of them into a sentence boundary. That produced a 36-character
# card snippet where 240 were available ("KARACHI: The commission met on
# Sept.") and rendered a paragraph break between "Dr." and the name after it.
_ABBREVIATIONS = frozenset(
    {
        "approx",
        "apr",
        "aug",
        "capt",
        "co",
        "col",
        "dec",
        "dept",
        "dr",
        "eng",
        "etc",
        "feb",
        "fig",
        "gen",
        "gov",
        "hon",
        "inc",
        "jan",
        "jr",
        "jul",
        "jun",
        "lt",
        "ltd",
        "maj",
        "mar",
        "mr",
        "mrs",
        "ms",
        "no",
        "nov",
        "oct",
        "prof",
        "pvt",
        "rev",
        "rs",
        "sept",
        "sep",
        "sgt",
        "sr",
        "st",
        "vs",
    }
)
_BOUNDARY_RE = re.compile(r"([.!?]+)(\s+)")
_TRAILING_WORD_RE = re.compile(r"([A-Za-z]+)$")


def split_sentences(text: str) -> List[str]:
    """Split into sentences, without breaking on a common abbreviation.

    A boundary is rejected when the word before the period is a known
    abbreviation or a single initial, or when what follows starts with a digit
    or a lowercase letter — a real sentence does not begin "16 in Islamabad".
    """
    clean = (text or "").strip()
    if not clean:
        return []

    sentences: List[str] = []
    start = 0
    for match in _BOUNDARY_RE.finditer(clean):
        head = clean[start : match.end(1)]
        following = clean[match.end() : match.end() + 1]
        if following and (following.islower() or following.isdigit()):
            continue
        trailing = _TRAILING_WORD_RE.search(clean[start : match.start(1)])
        if trailing:
            word = trailing.group(1)
            if word.lower() in _ABBREVIATIONS or len(word) == 1:
                continue
        piece = head.strip()
        if piece:
            sentences.append(piece)
        start = match.end()

    tail = clean[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


__all__ = ["split_sentences"]
