from __future__ import annotations

from src.agents.analysis import build_snippet
from src.utils.text import normalize_text, split_sentences


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


def test_zero_width_characters_are_removed():
    # 92 of 1680 live articles carried one; `\s` does not match them, so every
    # whitespace collapse in the pipeline left them in place and one reached a
    # published card.
    assert normalize_text("exchanged ​strikes") == "exchanged strikes"
    assert normalize_text("a‌b‍c⁠d﻿e­f") == "abcdef"


def test_unicode_spaces_fold_to_an_ordinary_space():
    assert normalize_text("Rs 500 million today") == "Rs 500 million today"


def test_whitespace_is_collapsed_and_trimmed():
    assert normalize_text("  two   words \n here ") == "two words here"


def test_normalization_is_nfc_not_nfkc():
    # NFKC would rewrite these into forms the number canonicalisation in
    # story_analysis has never been measured against.
    assert normalize_text("２０ per cent") == "２０ per cent"
    assert normalize_text("½ of the fund") == "½ of the fund"


def test_composed_and_decomposed_accents_compare_equal():
    decomposed = "Andre\u0301"  # e + combining acute
    composed = "Andr\u00e9"  # precomposed e-acute
    assert decomposed != composed
    assert normalize_text(decomposed) == normalize_text(composed) == composed


def test_normalization_is_idempotent():
    once = normalize_text("Rs 500 million ​paid")
    assert normalize_text(once) == once


def test_empty_and_none_are_safe():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""
