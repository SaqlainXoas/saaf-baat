"""Text normalization and splitting shared across ingest, editorial and analysis."""

from __future__ import annotations

import re
import unicodedata
from typing import List

# Characters that carry no meaning but survive every whitespace collapse,
# because `\s` does not match them. 92 of 1680 live articles carried one, and
# one reached a published card as "the US and Iran exchanged ​strikes" -
# invisible to a reader, but a real character to every token, keyword and
# number check downstream, and part of the text the embedder sees.
_INVISIBLE_RE = re.compile(r"[​-‍⁠﻿­]")
# Non-breaking and thin spaces read as one word to a human and as a non-space
# to `\s`-free comparisons; fold them to a plain space before collapsing.
_UNICODE_SPACE_RE = re.compile(r"[   ]")
# C0/C1 controls minus the whitespace ones, which the collapse handles.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def normalize_text(value: str) -> str:
    """Collapse whitespace and remove characters a reader cannot see.

    NFC, deliberately **not** NFKC. NFKC is the tempting one-liner and it is
    wrong here: it rewrites `1/2`, `%` and fullwidth digits into forms the
    number canonicalisation in `story_analysis` has never been measured
    against, and it perturbs far more of the embedded text than the defect
    being fixed. NFC composes accents and leaves the arithmetic alone.
    """
    text = _INVISIBLE_RE.sub("", value or "")
    text = _UNICODE_SPACE_RE.sub(" ", text)
    text = _CONTROL_RE.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()

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
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
# Short acronyms so common across unrelated stories that matching on them
# alone says nothing about shared identity - a courtesy-call story and a
# security incident can both mention "PM". Shared by every caller that
# extracts acronyms as an identity or relevance signal.
GENERIC_ACRONYMS = frozenset({"AJK", "CM", "DPM", "KP", "NA", "PA", "PM", "US", "UK"})


def extract_acronyms(text: str) -> set[str]:
    """Lowercase 2+ letter all-caps acronyms in text, excluding generic ones.

    "PSX" and "SBP" are as much an article's real subject as any longer word;
    a 4-character minimum on ordinary word tokenization drops them, which
    made a genuinely corroborated multi-source story render as single-sourced
    because the second article's headline only overlapped with the feed via
    "PSX".
    """
    return {
        match.lower() for match in _ACRONYM_RE.findall(text or "") if match not in GENERIC_ACRONYMS
    }


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


__all__ = ["normalize_text", "split_sentences", "extract_acronyms", "GENERIC_ACRONYMS"]
