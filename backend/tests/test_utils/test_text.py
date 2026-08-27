from __future__ import annotations

from src.agents.analysis import build_snippet
from src.utils.text import split_sentences


def test_an_abbreviation_is_not_a_sentence_boundary():
    # "Sept." and "Dr." are everywhere in this corpus.
    assert split_sentences("The court met on Sept. 16 in Islamabad. Dr. Uzma Khan spoke.") == [
        "The court met on Sept. 16 in Islamabad.",
        "Dr. Uzma Khan spoke.",
    ]


def test_an_initial_is_not_a_sentence_boundary():
    assert split_sentences("A. B. Khan spoke. Then he left.") == [
        "A. B. Khan spoke.",
        "Then he left.",
    ]


def test_ordinary_sentences_still_split():
    assert split_sentences("One thing. Two things. Three things.") == [
        "One thing.",
        "Two things.",
        "Three things.",
    ]


def test_text_without_terminal_punctuation_is_one_sentence():
    assert split_sentences("no terminal punctuation here") == ["no terminal punctuation here"]
    assert split_sentences("   ") == []


def test_snippet_is_not_cut_short_by_an_abbreviation():
    # Splitting on "Sept." made the first "sentence" 36 characters long, so the
    # card snippet was 36 characters where 240 were available.
    text = (
        "KARACHI: The commission met on Sept. 16 and issued notices to the victim's family, "
        "their lawyer, the provincial government's focal person and several senior police "
        "officers named in the original complaint filed this month. Next sentence."
    )
    snippet = build_snippet(text)

    assert len(snippet) > 180
    assert snippet.startswith("KARACHI: The commission met on Sept. 16 and issued")


def test_snippet_prefers_whole_sentences_over_a_mid_sentence_cut():
    text = "A first sentence that fits. Padding " + ("words " * 60) + "end."
    snippet = build_snippet(text)

    assert snippet == "A first sentence that fits."


def test_a_lowercase_word_after_a_period_does_not_start_a_sentence():
    # Real prose capitalises; a lowercase continuation means the period was
    # part of an abbreviation or a decimal, not a full stop.
    assert split_sentences("It rose to 22.5 per cent. and then fell") == [
        "It rose to 22.5 per cent. and then fell"
    ]
