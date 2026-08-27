from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.clustering import trusted_article_timestamp
from src.db.models import AnalyzedFeed, RawArticle

logger = logging.getLogger(__name__)
# Prompt lives in config/editorial_prompt.md — update there first
_EDITORIAL_PROMPT_PATH = Path(__file__).resolve().parents[2] / "config" / "editorial_prompt.md"
# The brief is 6-12 cards (AGENTS.md, changed 2026-08-28 from 10-12).
#
# Only the FLOOR moved. The cap never forced anything - padding pressure came
# from telling the editor that a full day is ten to twelve stories, and from a
# retry that ran until that number was reached. Lowering the cap to 10 was
# tried and reverted the same day: it cost the 2026-08-24 golden day a
# must-have topline outright (recall 100% -> 86%). A heavy news day really can
# hold twelve stories; an ordinary one holds six.
#
# The count was measured against the pool rather than chosen. One live day
# produced 320 clusters: 49 national hard-news, 20 local hard-news, the rest
# foreign, entertainment, sport or routine. Reading the 49 by hand, the stories
# where something actually changed for an ordinary reader numbered five strong
# and about three marginal - the remainder were reaffirmed commitments, denials,
# a flat market, agency PR and corporate results. A 10-12 target could only be
# met by admitting those, which is exactly how a bilateral defence protocol and
# a foreign-reserves total reached the brief.
DEFAULT_MAX_STORIES = 12
# What the prompt describes as a typical full news day. It is not a quota: the
# editor is told to return fewer when fewer candidates deserve a slot.
TARGET_STORY_FLOOR = 6
# The only count worth spending another call on. Retrying up to the target
# floor was structurally a padding mechanism - it pushed the editor down into
# the weak tail until the number was hit, which is how licence tallies and
# inspection drives reached the brief. This is a collapse guard instead, and it
# sits *below* TARGET_STORY_FLOOR for that reason: if the two were equal, the
# retry would once again be a mechanism for reaching the target.
COLLAPSE_RETRY_FLOOR = 4
# Retry a short pass this many times, each attempt seeing deeper into the
# ranked candidates, before shipping what the editor produced.
MAX_SHORT_PASS_ATTEMPTS = 3
# Above this many candidates the full-excerpt payload is mostly detail the
# editor does not decide on. Compacting keeps the prompt readable for the
# model and cheap in tokens.
COMPACT_PROMPT_CANDIDATE_THRESHOLD = 15

_DEFAULT_REPRESENTATIVE_EXCERPT_LIMIT = 420
_COMPACT_REPRESENTATIVE_EXCERPT_LIMIT = 260
VALID_CATEGORIES = (
    "economy",
    "politics",
    "city",
    "education",
    "health",
    "sports",
    "technology",
    "entertainment",
    "security",
    "international",
    "other",
)

VALID_IMPACT_LABELS = (
    "💳 WALLET",
    "🚦 COMMUTE",
    "🛡️ SAFETY",
    "🏢 WORK",
    "⚡ UTILITIES",
    "🏛️ GOVERNANCE",
)


@lru_cache(maxsize=1)
def _load_editorial_system_prompt() -> str:
    text = _EDITORIAL_PROMPT_PATH.read_text(encoding="utf-8").strip()
    marker = "## Prompt"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return text


EDITORIAL_SYSTEM_PROMPT = _load_editorial_system_prompt()


class EditorialError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClusterEditorialCandidate:
    cluster_id: UUID
    base_feed: AnalyzedFeed
    representative_article: RawArticle
    articles: Sequence[RawArticle]
    algorithm_used: str
    avg_similarity: Optional[float]
    min_member_similarity: Optional[float]

    def to_prompt_dict(
        self, *, compact: bool = False, excerpt_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        trusted_timestamps = [trusted_article_timestamp(article) for article in self.articles]
        latest_publish = max(trusted_timestamps).isoformat() if trusted_timestamps else None
        earliest_publish = min(trusted_timestamps).isoformat() if trusted_timestamps else None
        source_names = sorted({a.source for a in self.articles})
        supporting_headlines: List[str] = []
        for article in self.articles:
            headline = (article.headline or "").strip()
            if headline and headline not in supporting_headlines:
                supporting_headlines.append(headline)

        confirmed = [ent.text for ent in list(self.base_feed.confirmed_facts or [])[:3]]
        metadata = self.base_feed.metadata or {}
        if excerpt_limit is None:
            excerpt_limit = (
                _COMPACT_REPRESENTATIVE_EXCERPT_LIMIT
                if compact
                else _DEFAULT_REPRESENTATIVE_EXCERPT_LIMIT
            )

        evidence = dict(metadata.get("evidence") or {})
        if compact and evidence:
            # Only the fields the editor actually decides on. The prominence
            # integers and the triage confidence are ranking inputs the
            # orchestrator has already applied; carrying all twelve at thirty
            # candidates is a large payload spent on nothing the editor uses.
            evidence = {
                key: evidence[key]
                for key in ("source_count", "story_type", "pk_relevance", "hours_since_latest")
                if key in evidence
            }

        row = {
            "cluster_id": str(self.cluster_id),
            "algorithm_used": self.algorithm_used,
            "cluster_size": len(self.articles),
            "sources": source_names,
            "source_counts": dict(self.base_feed.source_attribution or {}),
            "latest_publish_date": latest_publish,
            "earliest_publish_date": earliest_publish,
            "representative_source": self.representative_article.source,
            "representative_headline": self.representative_article.headline,
            "representative_excerpt": _truncate(self.representative_article.main_text, excerpt_limit),
            "supporting_headlines": supporting_headlines[: (2 if compact else 4)],
            "deterministic_category": str(self.base_feed.category),
            "deterministic_impact_labels": list(self.base_feed.impact_labels or []),
            "deterministic_summary": _truncate(self.base_feed.summary or "", 180),
            # The facts the orchestrator gathered about this candidate
            # (CandidateEvidence). They were written to metadata one stage
            # earlier and then never shown to the editor, so it selected
            # without knowing a story's corroboration, its national reach or
            # whether triage called it a routine bulletin.
            "evidence": evidence,
            "publisher_topline_score": int(metadata.get("publisher_topline_score", 0) or 0),
            "publisher_topline_sources": list(metadata.get("publisher_topline_sources", [])),
            "confirmed_facts": confirmed,
        }
        if not compact:
            # Clustering diagnostics. Useful when reading a run by hand,
            # nothing an editor decides on, so they go first when space is tight.
            row["avg_similarity"] = _round_or_none(self.avg_similarity)
            row["min_member_similarity"] = _round_or_none(self.min_member_similarity)
        else:
            # Everything the editor does not decide on. `sources` already
            # carries the publishers, `evidence.hours_since_latest` already
            # carries freshness, and the excerpt already carries the summary.
            for key in (
                "source_counts",
                "algorithm_used",
                "earliest_publish_date",
                "latest_publish_date",
                "representative_source",
                "deterministic_summary",
                "confirmed_facts",
            ):
                row.pop(key, None)
        return row


class EditorialStory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The descriptions are load-bearing, not documentation: both providers are
    # driven by structured output, and a small model attends to a field
    # description far more reliably than to a line in the system prompt. The
    # impact_line rule in particular had no effect until it appeared here.
    cluster_id: str
    priority: int = Field(
        ge=0,
        le=100,
        description=(
            "How much this story matters, judged not ranked. Ties are allowed. "
            "Do not space values evenly across the brief."
        ),
    )
    headline: str = Field(min_length=8, max_length=180, description="10-12 words, active voice.")
    impact_line: str = Field(
        min_length=16,
        max_length=220,
        description=(
            "TWO PARTS, BOTH REQUIRED. Part one: name the people - commuters, "
            "parents, patients, traders, tenants, property buyers, students. "
            "Never 'observers', 'analysts', 'the market', 'stakeholders' or "
            "'parties to the case': those follow news for a living and are not "
            "the reader. "
            "Part two: name the one thing that is different for them today - a "
            "cost, a price, a deadline, a route, a document, a closure, a "
            "queue, a wait - something a reader could pay, miss, queue for, be "
            "turned away by, or read on a bill. Not a mood: 'a critical safety "
            "crisis', 'heightened scrutiny', 'growing concerns' describe an "
            "atmosphere, not a change. Present tense, about today. If you "
            "cannot fill both parts from the reporting, omit the story: you "
            "may not substitute a sentence about institutions, relations, "
            "ties, commitments, efforts or significance. Never 'may', "
            "'could', 'might', 'potential', 'helps', 'highlights', "
            "'underscores'. Never restate the headline. Vary the sentence - do "
            "not build every card as 'X face Y'. GOOD: 'Property buyers in "
            "Punjab lose six months of land record processing from today.' "
            "BAD: 'Military ties between the two nations strengthen after "
            "high-level meetings.' - no reader appears in it and nothing "
            "changed for anyone."
        ),
    )
    # Allowed values belong in the schema, not only in the validators: a
    # structured-output model cannot emit a value the enum does not contain,
    # and an invalid one here costs the whole card.
    category: str = Field(json_schema_extra={"enum": list(VALID_CATEGORIES)})
    # No enum here, deliberately. Gemini rejects an array-items enum inside
    # this schema with a bare 400 INVALID_ARGUMENT - it accepts the identical
    # construct in the smaller triage schema, and accepts the category and
    # public_impact enums here, so the limit is this schema's size rather than
    # the construct. The allowed labels are listed in the user prompt instead,
    # and the validator below still rejects anything outside the set.
    impact_labels: List[str] = Field(min_length=1, max_length=3)
    what_to_watch: Optional[str] = Field(
        default=None,
        max_length=180,
        description=(
            "OPTIONAL, and usually null. Fill it only when the reporting names "
            "a specific next event: a date, a hearing, a deadline, a vote, a "
            "scheduled decision, a figure due for release. 'The government "
            "will announce details soon', 'analysts will monitor the trend' "
            "and 'further directives will follow' are not next events - they "
            "are ways of saying nothing, and null is better than any of them. "
            "But when the reporting names a real one, it belongs HERE and not "
            "folded into the impact_line."
        ),
    )
    public_impact: str = Field(json_schema_extra={"enum": ["high", "medium", "watch"]})
    story_tags: List[str] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0, le=1)
    selection_reason: str = Field(
        min_length=12,
        max_length=220,
        description=(
            "Why this story earns a slot in a finite brief. For a legal, "
            "regulatory or trade-association ruling, this must quote the "
            "broad national consequence the supplied reporting itself states "
            "- a price consumers now pay, a nationwide supply or service "
            "effect, a rule binding a whole sector's customers. If the "
            "reporting does not state one, omit the story rather than "
            "describing what the ruling might lead to."
        ),
    )

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {value}")
        return value

    @field_validator("impact_labels")
    @classmethod
    def _validate_impact_labels(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in value:
            if item not in VALID_IMPACT_LABELS:
                raise ValueError(f"Invalid impact label: {item}")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned[:3]

    @field_validator("public_impact")
    @classmethod
    def _validate_public_impact(cls, value: str) -> str:
        if value not in {"high", "medium", "watch"}:
            raise ValueError(f"Invalid public_impact: {value}")
        return value

    @field_validator("story_tags")
    @classmethod
    def _validate_tags(cls, value: List[str]) -> List[str]:
        tags = [tag.strip() for tag in value if tag and tag.strip()]
        if not tags:
            raise ValueError("story_tags must contain at least one tag")
        return tags[:4]


class EditorialResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stories: List[EditorialStory] = Field(..., max_length=DEFAULT_MAX_STORIES)
    omitted_cluster_ids: List[str] = Field(default_factory=list)
    # "<cluster_id>: <reason>", one per well-corroborated national story the
    # editor chose to leave out. A plain list of strings on purpose: this is the
    # schema Gemini rejects an array-items enum inside with a bare 400, so it
    # gets no nested model and no enum of its own.
    omissions: List[str] = Field(default_factory=list)


MAX_PROMPT_CANDIDATES = 30


def candidate_windows(candidate_count: int, *, max_stories: int) -> List[int]:
    """How deep into the ranked candidates each successive attempt looks.

    The editor must see more candidates than the stories it may return, or a
    rejection can never be replaced.
    """
    limit = min(int(candidate_count), MAX_PROMPT_CANDIDATES)
    first = min(limit, max(int(max_stories) + 6, 12))
    windows = [first]
    while windows[-1] < limit and len(windows) < MAX_SHORT_PASS_ATTEMPTS:
        windows.append(min(limit, windows[-1] + 8))
    return windows


def review_with_short_pass_retries(
    review_once: Callable[[Sequence[ClusterEditorialCandidate]], EditorialResponse],
    candidates: Sequence[ClusterEditorialCandidate],
    *,
    max_stories: int,
) -> Dict[UUID, EditorialStory]:
    """
    Ask the editor for the brief, retrying only a collapsed pass.

    A pass that comes back near-empty is retried against a deeper slice of the
    ranked candidates: the editor rejecting the top of the list is exactly when
    it needs to see further down it. The trigger is COLLAPSE_RETRY_FLOOR, not
    the ten-to-twelve target - retrying up to the target was structurally a
    padding mechanism, pushing the editor into the weak tail until the number
    was hit. After the attempts are spent the caller ships what the editor
    produced; padding the count with template cards is what this replaces.
    """
    if not candidates:
        return {}

    floor = min(COLLAPSE_RETRY_FLOOR, int(max_stories), len(candidates))
    best: Dict[UUID, EditorialStory] = {}
    last_error: Optional[EditorialError] = None

    for attempt, window in enumerate(
        candidate_windows(len(candidates), max_stories=max_stories), start=1
    ):
        prompt_candidates = list(candidates[:window])
        try:
            parsed = review_once(prompt_candidates)
        except EditorialError as exc:
            last_error = exc
            logger.warning("Editorial attempt %d failed: %s", attempt, exc)
            break

        by_cluster = _stories_by_cluster_id(parsed, prompt_candidates)
        _log_corroborated_omissions(parsed, prompt_candidates, by_cluster)
        _log_thin_admissions(prompt_candidates, by_cluster)
        if len(by_cluster) > len(best):
            best = by_cluster
        if len(best) >= floor:
            break

        logger.info(
            "Editorial attempt %d returned %d stories, below the collapse floor "
            "of %d (saw %d/%d candidates)",
            attempt,
            len(by_cluster),
            floor,
            window,
            len(candidates),
        )

    if not best and last_error is not None:
        raise last_error
    return best



# A well-corroborated national story the editor drops is a product decision, not
# a bug — but it must never be an invisible one. On 2026-08-25 the day's
# most-covered story (7 sources) was dropped for a procedural headline and
# nothing anywhere recorded that it had happened.
CORROBORATION_ACCOUNTING_MIN_SOURCES = 4


def _candidate_evidence(candidate: ClusterEditorialCandidate) -> Dict[str, Any]:
    return dict((candidate.base_feed.metadata or {}).get("evidence") or {})


def _evidence_source_count(candidate: ClusterEditorialCandidate) -> int:
    try:
        return int(_candidate_evidence(candidate).get("source_count") or 0)
    except (TypeError, ValueError):
        return 0


def _log_thin_admissions(
    prompt_candidates: Sequence[ClusterEditorialCandidate],
    published: Dict[UUID, EditorialStory],
) -> None:
    """Record a card admitted over better-corroborated national candidates.

    The mirror of _log_corroborated_omissions, and added for the same reason.
    On 2026-08-27 a two-source competition-commission penalty over ghee pricing
    reached the brief while a three-source national story attached to the day's
    biggest event did not. That is the editor's call to make - but nothing
    anywhere recorded that the trade had happened, so the only way to find it
    was to read the whole candidate pool by hand afterwards.
    """
    dropped_national = [
        candidate
        for candidate in prompt_candidates
        if candidate.cluster_id not in published
        and str(_candidate_evidence(candidate).get("pk_relevance") or "") == "national"
    ]
    if not dropped_national:
        return

    for candidate in prompt_candidates:
        if candidate.cluster_id not in published:
            continue
        source_count = _evidence_source_count(candidate)
        # Only a *thin* card is worth reporting. Comparing every published card
        # against the single best-corroborated dropped one warned on 8 of 8
        # cards in a live run, which is not accounting - it is noise that
        # buries the one line worth reading.
        if source_count >= CORROBORATION_ACCOUNTING_MIN_SOURCES:
            continue
        better = sorted(
            (
                (_evidence_source_count(other), (other.base_feed.headline or "").strip()[:70])
                for other in dropped_national
                if _evidence_source_count(other) > source_count
            ),
            reverse=True,
        )[:2]
        logger.warning(
            "Editor published a %d-source card over %d better-corroborated national "
            "candidate(s): %s -- passed over %s",
            source_count,
            len(better),
            (candidate.base_feed.headline or "").strip()[:90],
            "; ".join(f"{count}-source {headline}" for count, headline in better),
        )


def _log_corroborated_omissions(
    parsed: "EditorialResponse",
    prompt_candidates: Sequence[ClusterEditorialCandidate],
    published: Dict[UUID, EditorialStory],
) -> None:
    """Record every well-corroborated national candidate the editor left out."""
    stated: Dict[str, str] = {}
    for entry in getattr(parsed, "omissions", []) or []:
        cluster_id, _, reason = str(entry).partition(":")
        stated[cluster_id.strip()] = reason.strip() or "(no reason given)"

    for candidate in prompt_candidates:
        if candidate.cluster_id in published:
            continue
        evidence = _candidate_evidence(candidate)
        source_count = _evidence_source_count(candidate)
        if source_count < CORROBORATION_ACCOUNTING_MIN_SOURCES:
            continue
        if str(evidence.get("pk_relevance") or "") != "national":
            continue

        headline = (candidate.base_feed.headline or "").strip()[:90]
        reason = stated.get(str(candidate.cluster_id))
        if reason:
            logger.info(
                "Editor omitted a %d-source national story and gave a reason: %s (%s)",
                source_count,
                headline,
                reason,
            )
        else:
            logger.warning(
                "Editor dropped a %d-source national story without accounting for it: %s",
                source_count,
                headline,
            )

def _stories_by_cluster_id(
    parsed: EditorialResponse,
    candidates: Sequence[ClusterEditorialCandidate],
) -> Dict[UUID, EditorialStory]:
    """Map a parsed response onto the clusters it was actually allowed to pick."""
    by_cluster: Dict[UUID, EditorialStory] = {}
    allowed_ids = {candidate.cluster_id for candidate in candidates}
    for story in parsed.stories:
        try:
            cluster_id = UUID(story.cluster_id)
        except ValueError:
            logger.warning("Ignoring editorial story with invalid cluster_id=%s", story.cluster_id)
            continue
        if cluster_id not in allowed_ids:
            logger.warning("Ignoring editorial story for unknown cluster_id=%s", cluster_id)
            continue
        if cluster_id in by_cluster:
            continue
        by_cluster[cluster_id] = story
    return by_cluster


def merge_editorial_story(
    candidate: ClusterEditorialCandidate,
    story: EditorialStory,
    *,
    model_name: str,
) -> AnalyzedFeed:
    feed = candidate.base_feed.model_copy(deep=True)
    feed.headline = story.headline.strip()
    feed.category = story.category
    feed.impact_labels = story.impact_labels

    metadata = dict(feed.metadata or {})
    metadata.update(
        {
            "editorial_model": model_name,
            "editorial_priority": int(story.priority),
            "editorial_confidence": float(story.confidence),
            "editorial_grade": story.public_impact,
            "impact_line": story.impact_line.strip(),
            "why_it_matters": story.impact_line.strip(),
            "what_to_watch": (story.what_to_watch or "").strip(),
            "story_tags": list(story.story_tags),
            "selection_reason": story.selection_reason.strip(),
            "cluster_algorithm": candidate.algorithm_used,
            "cluster_avg_similarity": _round_or_none(candidate.avg_similarity),
            "cluster_min_member_similarity": _round_or_none(candidate.min_member_similarity),
            "representative_source": candidate.representative_article.source,
            "representative_headline": candidate.representative_article.headline,
            "llm_augmented": True,
        }
    )
    feed.metadata = metadata
    return feed


def build_editorial_user_prompt(candidate_rows: Sequence[Dict[str, Any]], *, max_stories: int) -> str:
    target_cap = max(1, min(int(max_stories), DEFAULT_MAX_STORIES))
    typical_floor = min(TARGET_STORY_FLOOR, target_cap)
    return json.dumps(
        {
            "task": "Select and format the morning brief.",
            "allowed_categories": list(VALID_CATEGORIES),
            # Not expressible in the response schema (see EditorialStory), so
            # the prompt is the only place the editor learns the allowed set.
            "allowed_impact_labels": list(VALID_IMPACT_LABELS),
            "allowed_public_impact": ["high", "medium", "watch"],
            "typical_story_range": {"min": typical_floor, "max": target_cap},
            "max_stories": target_cap,
            "selection_rules": [
                "Return at most max_stories items in stories.",
                "typical_story_range describes a full news day, not a quota. Return fewer stories when fewer candidates deserve a slot, and never pad the count to reach the range.",
                "Each story must map to exactly one provided cluster_id.",
                "Every card must earn its slot: include it only if an ordinary reader in Pakistan would be worse off not knowing it by this evening.",
                "evidence carries what the pipeline knows about each candidate. Use evidence.pk_relevance and evidence.source_count to judge whether a story is real and national - never as a reason to publish it.",
                "A high evidence.source_count often means a ministry or a military press office issued a statement that every publisher reprinted. Syndication is not importance. A bilateral protocol, a reaffirmed commitment, an expanded cooperation, a courtesy call or a reviewed progress carried by seven publishers is still a card with no reader in it, and it must lose its slot to a story that changes something for someone.",
                "evidence.story_type of 'routine' marks an institution publicising its own activity: licence and inspection tallies, campaign totals, routine transfers, ceremonial visits. Include one only when it carries a real consequence for readers, and never above a national development.",
                "publisher_topline_score measures position in a publisher's feed, not importance. Use it only to break a tie between otherwise equal candidates.",
                "Do not let an isolated local incident lead the brief when a national development is available.",
                "A narrow legal, regulatory or trade-association ruling earns a slot only when the supplied reporting itself states a broad, immediate national consequence - a price ordinary consumers now pay, a nationwide supply or service effect, or a rule binding a whole sector's customers from a stated date. A consumer-adjacent topic is not that consequence, and such a ruling must never displace a security incident, a disaster, a major price change, or a nationally consequential political development.",
                "headline must be 10-12 words, active voice, and direct.",
                "impact_line is two parts and both are required: name the people, then name the one thing that is different for them today. Apply that as a test, not as advice - read your own line back and point at the people in it and at what changed. If you cannot point at both, omit the story.",
                "impact_line must never restate the headline in different words, and must never be a generic observation such as 'this highlights ongoing challenges' or 'this could affect public perception'. A sentence whose subject is an institution, a relationship or a process - 'ties strengthen', 'cooperation expands', 'the commission enforces' - has no reader in it and fails the test.",
                "Part two must be a fact a reader could pay, miss, queue for or read on a bill - not a mood such as 'a critical safety crisis', 'heightened scrutiny' or 'growing concerns'. Never use 'potential' or 'potentially' to smuggle a hedge past the ban on 'may' and 'could'.",
                "Vary the sentence across the brief. Do not write every impact_line as 'X face Y' - eight cards from one template read as a machine however accurate each line is.",
                "what_to_watch is optional and usually null. Fill it only when the reporting names a specific next event: a date, a hearing, a deadline, a vote, a scheduled decision. Never write that something will be announced soon, monitored, reviewed or followed up - omit the field instead.",
                "priority is your judgement of how much a story matters, from 0 to 100. Ties are allowed. Do not space the values evenly - an evenly spaced sequence says you ranked by position rather than by importance.",
                "Use impact_labels only from the allowed set.",
                "impact_line and what_to_watch must stay grounded in provided evidence.",
                "Never use passive voice.",
                "Never write vague attribution like 'sources say'.",
                "If you cannot write a confident impact_line, omit the cluster.",
            ],
            "candidates": list(candidate_rows),
        },
        ensure_ascii=False,
    )


def _truncate(text: str, limit: int) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _round_or_none(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _normalize_editorial_payload(
    payload: Dict[str, Any],
    candidate_lookup: Dict[str, ClusterEditorialCandidate],
) -> Dict[str, Any]:
    # json_object mode sometimes returns the array itself rather than an
    # object wrapping it. That cost a whole editorial pass to
    # "'list' object has no attribute 'get'" on a live run.
    if isinstance(payload, list):
        stories: Any = payload
    else:
        stories = payload.get("stories")
    if not isinstance(stories, list):
        stories = []

    normalized_stories: List[Dict[str, Any]] = []
    for item in stories:
        if not isinstance(item, dict):
            continue
        cluster_id = str(item.get("cluster_id") or "").strip()
        if not cluster_id:
            continue
        candidate = candidate_lookup.get(cluster_id)
        if candidate is None:
            continue

        base_feed = candidate.base_feed
        priority = item.get("priority")
        if not isinstance(priority, int):
            priority = min(95, max(50, 45 + (10 * len(candidate.articles))))

        impact_labels = item.get("impact_labels")
        if not isinstance(impact_labels, list):
            impact_labels = []
        impact_labels = [label for label in impact_labels if label in VALID_IMPACT_LABELS]
        if not impact_labels:
            impact_labels = list(base_feed.impact_labels or ["🏛️ GOVERNANCE"])

        category = item.get("category") or str(base_feed.category)
        if category not in VALID_CATEGORIES:
            category = str(base_feed.category)
        public_impact = item.get("public_impact")
        if public_impact not in {"high", "medium", "watch"}:
            public_impact = "high" if priority >= 80 else "medium"
        story_tags = item.get("story_tags")
        if not isinstance(story_tags, list) or not story_tags:
            story_tags = _default_story_tags(candidate)

        impact_line = str(item.get("impact_line") or item.get("why_it_matters") or "").strip()
        if not impact_line:
            continue
        # A missing what_to_watch used to become "Watch for the next official
        # update." - template copy entering an LLM-written brief through the
        # back door. It then dropped the whole story instead, which was too far
        # the other way: measured on a live brief, 6 of 7 of these lines said
        # only that something else would happen later. The field is optional
        # now, so a story with nothing real to watch keeps its card and loses
        # the line. Template copy is still never written.
        what_to_watch = str(item.get("what_to_watch") or "").strip()
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.65

        normalized_stories.append(
            {
                "cluster_id": cluster_id,
                "priority": int(priority),
                "headline": item.get("headline") or base_feed.headline,
                "impact_line": impact_line,
                "category": category,
                "impact_labels": impact_labels,
                "what_to_watch": what_to_watch,
                "public_impact": public_impact,
                "story_tags": story_tags,
                "confidence": float(confidence),
                "selection_reason": item.get("selection_reason") or "Selected by editorial review.",
            }
        )

    omitted = payload.get("omitted_cluster_ids") if isinstance(payload, dict) else None
    if not isinstance(omitted, list):
        omitted = []

    omissions = payload.get("omissions") if isinstance(payload, dict) else None
    if not isinstance(omissions, list):
        omissions = []

    return {
        "stories": normalized_stories,
        "omitted_cluster_ids": [str(item) for item in omitted if item],
        "omissions": [str(item).strip() for item in omissions if str(item).strip()],
    }


def _default_story_tags(candidate: ClusterEditorialCandidate) -> List[str]:
    tags: List[str] = []
    tags.append(str(candidate.base_feed.category))
    for fact in candidate.base_feed.confirmed_facts[:2]:
        text = fact.text.strip().lower().replace(" ", "-")
        if text and text not in tags:
            tags.append(text)
    if len(tags) == 1:
        tags.append(candidate.representative_article.source)
    return tags[:4]


__all__ = [
    "COLLAPSE_RETRY_FLOOR",
    "COMPACT_PROMPT_CANDIDATE_THRESHOLD",
    "DEFAULT_MAX_STORIES",
    "EDITORIAL_SYSTEM_PROMPT",
    "MAX_PROMPT_CANDIDATES",
    "TARGET_STORY_FLOOR",
    "ClusterEditorialCandidate",
    "EditorialError",
    "EditorialResponse",
    "EditorialStory",
    "build_editorial_user_prompt",
    "candidate_windows",
    "merge_editorial_story",
    "review_with_short_pass_retries",
]
