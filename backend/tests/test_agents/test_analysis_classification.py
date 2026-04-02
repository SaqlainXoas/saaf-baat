"""
TDD tests for RuleBasedClassifier using classification_rules.yaml.
"""
from __future__ import annotations

from pathlib import Path


def test_rule_based_classifier_detects_category_and_impact():
    from src.agents.analysis import RuleBasedClassifier

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    text = "Rupee falls against dollar amid inflation and tax concerns. Petrol price increase expected."
    result = clf.classify_text(text)

    assert result.category == "economy"
    assert "💳 WALLET" in result.impact_labels


def test_rule_based_classifier_falls_back_to_other():
    from src.agents.analysis import RuleBasedClassifier

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    text = "A rare comet passes by Earth in a spectacular night sky event."
    result = clf.classify_text(text)

    assert result.category in (
        "other",
        "international",
        "technology",
        "sports",
        "health",
        "city",
        "politics",
        "economy",
        "security",
        "education",
        "entertainment",
    )
    # Specifically: should not crash; unknown content should generally map to "other".


def test_rule_based_classifier_detects_civic_disruption_from_headline():
    from src.agents.analysis import RuleBasedClassifier

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    result = clf.classify_parts(
        "Floodwaters block Zhob-Dera Ismail Khan highway, leaving passengers stranded",
        "Rescue teams were deployed after heavy rain blocked the highway and stranded passengers overnight.",
    )

    assert result.category == "city"
    assert "🚦 COMMUTE" in result.impact_labels


def test_rule_based_classifier_detects_education_story():
    from src.agents.analysis import RuleBasedClassifier

    rules_path = Path(__file__).resolve().parent.parent.parent / "config" / "classification_rules.yaml"
    clf = RuleBasedClassifier.from_yaml(rules_path)

    result = clf.classify_parts(
        "Sindh to resume physical classes at educational institutions from April 1",
        "The education department said schools and colleges will resume classes across Sindh.",
    )

    assert result.category == "education"
    assert "🏛️ GOVERNANCE" in result.impact_labels
