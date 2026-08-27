"""
TDD tests for EntityExtractor.

We inject a small spaCy pipeline (blank + EntityRuler) so tests do not
depend on external model downloads.
"""
from __future__ import annotations


def test_entity_extractor_extracts_allowed_labels_only():
    import spacy

    from src.agents.analysis import EntityExtractor

    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns(
        [
            {"label": "PERSON", "pattern": "Imran Khan"},
            {"label": "ORG", "pattern": "State Bank of Pakistan"},
            {"label": "GPE", "pattern": "Islamabad"},
            {"label": "MONEY", "pattern": "Rs 300"},
        ]
    )
    extractor = EntityExtractor(nlp=nlp)

    text = "Imran Khan met officials at the State Bank of Pakistan in Islamabad. Fine of Rs 300 imposed."
    entities = extractor.extract(text)

    labels = {e.type for e in entities}
    assert "PERSON" in labels
    assert "ORG" in labels
    assert "GPE" in labels
    assert "MONEY" in labels


def test_entity_extractor_normalizes_entity_text():
    import spacy

    from src.agents.analysis import EntityExtractor

    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler")
    # Token pattern matches regardless of multiple spaces in source text
    ruler.add_patterns([{"label": "PERSON", "pattern": [{"LOWER": "imran"}, {"LOWER": "khan"}]}])
    extractor = EntityExtractor(nlp=nlp)

    # Extra whitespace should normalize to a stable display string
    text = "Imran   Khan visited Islamabad."
    entities = extractor.extract(text)

    assert any(e.text == "Imran Khan" for e in entities)
