# CLAUDE.md — Working Guide for Saaf Baat

Operational guide for Claude Code sessions. Product decisions and the end
vision live in `AGENTS.md`; current state and open work live in `docs/status.md`.
Read this file first — it is the architecture reference.

## What this product is (one paragraph)

Saaf Baat is a **finite daily Pakistan morning brief**: 6–12 cards that tell an
ordinary reader what happened, why it matters to their life, and what to watch
next — then it ends on purpose. It is explicitly *not* an infinite feed, not a
rolling hourly wire, and not a summarizer of every article published. The
success test is not "did the pipeline run" but "does this set of cards look
like today's real Pakistan toplines to a Pakistani reader".

## Session start checklist

1. **`docs/status.md`** — start here. What ships, the measured verification
   state, and what is still open.
2. `AGENTS.md` — locked product decisions (do not contradict without asking)
3. The rest of this file — the architecture, and why each threshold is what it is.

Deployment instructions live in `docs/deployment.md`. README screenshots live in
`assets/` and are tracked; `docs/` is gitignored in full, so anything the README
links to must live outside it or GitHub serves a 404 to every visitor. `claude-thinking-notes/`, `codex-thinking/`
and `program.md` were deleted on 2026-08-28: they were session records of work
that is finished, and everything in them that stayed true is in this file or in
`docs/status.md`. Re-runnable ingest evidence lives in `backend/scripts/research/`.

There is deliberately no `architecture.md`. It was deleted on 2026-08-27: it
described `HybridOrchestrator`, Playwright, the parser ensemble,
`RuleBasedClassifier`, `_candidate_publish_score`, Groq editorial and a 0.80
grouping threshold, none of which exist any more. **This file is the
architecture reference.** A stale architecture doc is worse than none, because
it is the file a new session reads second.

## Environment

- Python venv: `backend/venv` — **activate before any Python command**
  (`source backend/venv/bin/activate`). There is no system `python` on PATH.
- Node: Homebrew at `/opt/homebrew/bin/node` (v25). Prefix PATH with
  `/opt/homebrew/bin`.
- Backend env: `backend/.env` (template in `backend/.env.example`).

## Database — local SQLite (default)

Local development defaults to SQLite. The hosted setup uses Supabase for shared storage, Render for the API, Vercel for Next.js and GitHub Actions for generation. See `docs/deployment.md`.

- Backend selection: `SAAF_DB_BACKEND` — `sqlite` (default) or `supabase`.
- File location: `SAAF_SQLITE_PATH`, default `backend/data/saafbaat.db`.
- Schema: `backend/src/db/schema_sqlite.sql` for local SQLite. Hosted Postgres
  changes are versioned in `supabase/migrations/`; `backend/src/db/schema.sql`
  remains a readable schema snapshot, not the production migration command.
- Init/inspect: `python scripts/init_db.py` (`--reset` wipes local data).

**Always build clients via `src.db.factory.create_db_client()`.** Do not import
`SqliteClient` or `SupabaseClient` directly outside `src/db/`. Both implement
the same method surface, so a future Postgres swap should touch `factory.py`
and one new client file only.

Storage encoding notes that matter when writing queries:
- UUIDs are TEXT; timestamps are fixed-width ISO-8601 UTC TEXT, so lexical
  ordering equals chronological ordering. Naive datetimes are read as UTC.
- Embeddings, metadata, and array columns are JSON TEXT. Vector math happens in
  numpy inside the pipeline — the database does no similarity work.

## Ingestion — RSS + news sitemaps (no HTML scraping)

Two deterministic discovery channels, merged on canonical URL:
`scrapers/feeds.py` reads each publisher's RSS feeds and Google-News sitemap in
parallel (~26 endpoints, ~6s, ~300 articles/day).

- **Never trust an HTTP 200.** Every endpoint is gated on the age of its newest
  item; older than 48h and the whole endpoint is quarantined, surfaced in
  `PipelineStats.degraded_sources`, the heartbeat, and `/health`.
- **Tier A** (`dawn`, `tribune`, `brecorder`) ship full article text in RSS.
  **Tier B** (`geo`, `ary`, `nation`, `app`, `thenews`) supply headline +
  summary and exist to answer "is anyone else covering this?".
- **Body fetching is lazy** — `scrapers/body.py` fetches a page only for a
  selected story's representative article that has no usable text, roughly a
  dozen requests per run. Playwright and the parser ensemble are gone;
  trafilatura and `StealthFetcher`'s rate limiting remain.
- `metadata.body_status` is `full` / `summary` / `headline_only`. A row with
  only a headline is valid and expected.
- The embedding free tier bills **one request per text, 100/minute**, so
  `embed_batch` paces itself. This, not clustering, is what makes a full run
  take minutes.

## Triage and adjudication — LLM where it changes the outcome

`config/classification_rules.yaml` and `RuleBasedClassifier` are **gone**.
Category and impact come from `agents/triage.py`: batched Gemini triage over
~50 headlines per call, run per article after embedding, persisted to
`metadata.triage` so a re-run does not re-pay. A verdict carries `category`,
`impact_labels`, `story_type` and `pk_relevance`; `AnalysisService` aggregates
the members' verdicts into the cluster's.

- **An article with no verdict is not publishable.** That is a state, not a
  guess — `triage_status` in the heartbeat and `/health` says why.
- `agents/adjudication.py` resolves only split/merge pairs the deterministic
  gates leave genuinely ambiguous: similarity near the threshold, the two
  signals disagreeing, **and at least two shared headline tokens**. Entity
  overlap is generic-name noise on this corpus and must not be used for the
  floor. Typical cost is 1–3 calls/day. The adjudicator proposes; the group
  coherence gates still veto.
- Budget: ~11 triage + ~3 adjudication + 1–3 editorial ≈ **16 calls/day**.
- **Keep the ingest layer LLM-free.**
- The enumerated fields (`category`, `story_type`, `pk_relevance`,
  `impact_labels`) carry their allowed values **in the response schema**, so a
  structured-output model cannot answer `category: "opinion"`. The one
  exception is the editor's `impact_labels`: Gemini rejects an array-items enum
  inside that larger schema with a bare 400, so its allowed set lives in the
  user prompt instead. Do not "fix" that by adding the enum back.

## Grouping — the threshold is corpus-specific

`event_group_min_pair_similarity` is **0.92**, and it is not a knob to round
down. Pakistani political wire copy embeds into a narrow band: two reports of
the *same* event sit at 0.95-0.97, two *different* events in the same domain at
about 0.82. At the old 0.80 floor everything political chained together through
single linkage — one live cluster held Imran Khan's hospital transfer, the Munir
visit to Iran, a PM meeting and a Turkiye FMs call, and was represented by the
single-article FM call, so the day's two biggest stories were invisible to the
editor while a minor one inherited their corroboration.

The `min_intra_cluster_similarity` / `min_member_similarity_to_centroid` gates
were measured to make **no difference at any setting**; the pair threshold does
all the work. Do not tune them without evidence.

**`event_group_max_time_delta_hours` is 36, deliberately equal to
`article_max_age_hours`.** A grouping window narrower than the ingest window is
a structural ceiling on exactly the biggest stories: two articles can sit in the
same pool, embed at 0.97, pass every overlap gate, and still be barred from one
cluster purely by age gap. It was 18h, and on 2026-08-27 the PIMS hospital fire
ran 30.5h from the blaze to the funerals — so it split into a 4-article
/2-source cluster headed by the fire and a separate 5-article/4-source cluster
headed by the burials, and the day's biggest story showed the editor 2-source
corroboration. At 36h it is one 8-article/5-source cluster under the right
headline. Long-running stories are the ones a brief must lead with, and they
were the only ones this gate could hit. Swept over all three fixtures at
18/24/30/36: `merged-in` never rose and fell 9→7 on 2026-08-27, split fell
38→33, recall was unchanged. Do not narrow it without re-running that sweep.

**Adjudication is a no-op in the golden-day replay.** No fixture has an
`adjudication.json` and `capture_golden_day.py` has never written one, so
`RecordedAdjudicator` answers nothing and every ambiguous pair falls through to
the deterministic split. Live runs adjudicate ~24 pairs and merge ~13 of them.
The grouping numbers the harness prints are therefore measured against a weaker
grouper than production runs — `eval_golden_day.py` now says so on every run.
Recording real verdicts at capture time is unbuilt work, not a setting.

**The golden day cannot see a grouping regression on its own** — recall was 100%
at every threshold, because keyword matching finds its must-have inside a blob
as happily as inside a clean cluster. `measure_cluster_quality` scores grouping
against an embedding-only reference partition and `max_merged_articles` in each
`expected.yaml` ratchets it. Read that number, not just recall.

**Cluster analysis is ordered by size, not recency.** `get_all_clusters` takes
`order="size"`, because the limit truncates and dropping by write order once hid
a 7-source topline. Hitting the limit logs a warning; raise
`analyze_recent_clusters_limit` rather than ignoring it.

## Selection — facts, not a score

`_candidate_publish_score` is gone. `CandidateEvidence` carries source count,
feed prominence, freshness and the triage verdict; it is passed to the editor
and ordered **lexicographically** when no editor is available. Do not
reintroduce a weighted sum — the old one saturated at 100 for every published
card, so ranking meant nothing.

Deterministic exclusions are only what must never be negotiable: hard category
exclusions, excluded story types, no-Pakistan-relevance, staleness,
near-duplicate suppression, per-source caps. Everything else is the editor's
call. A rejection logs one named cause.

Brief size is **6–12**, changed from 10–12 on 2026-08-28. It is encoded in
`PipelineConfig`, `.env.example`, `config/editorial_prompt.md`,
`agents/editorial.py` (`DEFAULT_MAX_STORIES`, `TARGET_STORY_FLOOR`,
`EditorialResponse.stories`), `frontend/src/data/briefSize.ts` and the
`brief_size` block in every `expected.yaml`. Change them together.

**The count was measured against the pool, not chosen.** One live day produced
320 clusters — 49 national hard-news, 20 local hard-news, the rest foreign,
entertainment, sport or routine. Read by hand, the 49 held five strong stories
where something changed for an ordinary reader and about three marginal ones;
the remainder were reaffirmed commitments, denials, a flat market, agency PR
and corporate results. A 10–12 target is only reachable by admitting those,
which is how a bilateral defence protocol and a foreign-reserves total reached
the brief. **Do not raise the floor again without re-running that count.**

**Only the floor moved.** Lowering the cap to 10 was tried on 2026-08-28 and
reverted within the hour: it cost the 2026-08-24 golden day a must-have topline
outright, recall 100% -> 86%. The cap never forced padding; the floor did.

`COLLAPSE_RETRY_FLOOR` equals `TARGET_STORY_FLOOR` (6): any pass returning
fewer than six stories retries against deeper candidates before the product
accepts a short edition. It sat deliberately *below* the target floor (4)
until 2026-09-02, specifically because an equal floor would turn the retry
into a mechanism for reaching a quota. It is safe to equal the target now
because two guards were added alongside the change:
`_editorial_story_is_grounded` rejects any story whose headline, impact line
or `what_to_watch` claims a number, a consequence, or an active government
move the supplied reporting does not itself state, so a retry cannot pad the
brief with a fabricated claim the way the old quota-retry could; and
`review_with_short_pass_retries` excludes a cluster from every subsequent
attempt once it has failed that grounding check once, so a retry spends its
budget on candidates the editor hasn't judged yet rather than re-proposing
and re-rejecting the same story. A live run on 2026-09-02 with the old 4-vs-6
split still only reached four cards while burning two of its three retry
attempts re-offering clusters already rejected for lack of grounding — the
equal floor plus the two guards above is the fix for that failure mode, not a
reversion to the padding this section originally warned against.

**An editorial outage publishes nothing.** `editorial_status` distinguishes
`unavailable` (the editor was meant to run and could not) from `disabled` (it
was switched off deliberately, as the golden-day harness does). Only the second
writes deterministic cards. An outage leaves the previous brief standing, and
`/api/feed` serves it as stale under "Latest brief" — yesterday's real
journalism honestly labelled beats today's template copy dressed as news. This
is why `remediate_recent_clusters` deletes clusters but never `analyzed_feed`
rows: deleting the standing brief before an editorial pass that then publishes
nothing leaves the reader two days behind.

**Never back-fill the brief with template copy.** Every pass under the
six-card floor retries against deeper candidates rather than shipping short —
but retrying never means padding. `_editorial_story_is_grounded` still
rejects any story whose claims outrun the supplied reporting on every
attempt, and a cluster that fails it is excluded from later attempts so the
editor cannot re-select and re-fail the same story instead of reviewing a new
one. After `MAX_SHORT_PASS_ATTEMPTS` the caller ships whatever the editor
actually grounded, even if that is still short of six. Retrying up to a fixed
target count regardless of grounding was the original padding mechanism — it
pushed the editor down into the weak tail until a number was hit, which is
how licence tallies and inspection drives once reached the brief. The
fallback dictionaries exist only for total provider unavailability, and that
surfaces as `editorial_status` in `/health`.

**Gemini is the only editorial provider.** Groq and `editorial_router.py` were
deleted on 2026-08-25. Groq's free tier allows **8,000 tokens per minute** for
`openai/gpt-oss-120b`, prompt and completion together — its 413 is a rate-limit
error wearing a size code — and a full brief over a 30-candidate
shortlist does not fit. Every run spent a 413, a ~40s backoff and a
fall-through before Gemini produced the brief anyway.

**The editor is shown `CandidateEvidence`.** `to_prompt_dict` carries the
`evidence` block (source count, `story_type`, `pk_relevance`, freshness). It
was written to metadata and shown to nobody until 2026-08-25, so the editor
ranked without knowing a story's corroboration or national reach.
`publisher_topline_score` is a tiebreak only: it measures feed position, and it
once scored a food-inspection drive above the Army Chief's Tehran trip.

**The brief is one run's output, not an accumulation.** Every published card
carries `metadata.brief_run_at`, and `/api/feed` serves only the newest stamp.
Without it, a cluster the editor dropped kept its row: a live check served
eleven cards for an eight-card brief, two of them the same story under two
headlines written hours apart.

## Quality evaluation — the golden day

**The default run has the editor off**, so it scores selection and ordering,
not the brief production ships. `--live-editorial` replays the same recorded
day through the real editor (~1–3 LLM calls) and is the only way to A/B a
prompt change without waiting for tomorrow's news. It reports and never gates:
the editor is nondeterministic, and the `baseline_recall` ratchet belongs to
the offline run alone. It also reports two impact-line signals — how many lines
restate their headline, and how many carry no number, price or named day. Those
are tuning signals, not verdicts; a good line can carry no number.

**Expectations are derived, not judged.** `scripts/derive_expectations.py`
builds `must_have` from a fact in the fixture — how many distinct publishers ran
the story, over the same pool the pipeline ingests — and splits the result three
ways: corroborated + `national` is a must-have, corroborated + tripping a hard
gate is a must-not-have, and corroborated + `foreign_with_pk_effect`/`local` is
the editor's call and is reported, never asserted. Two calibration rules learned
the hard way: capture at **40 articles per source**, because at 15 no story
clears three publishers and the oracle finds nothing; and never drop a keyword
just because the corpus is full of it, because the identifying name of a topline
is corpus-common by definition. `2026-08-24` stays hand-drafted over its thinner
pool — see its header.

`python scripts/eval_golden_day.py` replays a recorded news day
(`tests/fixtures/golden_days/`) through the real pipeline, offline, in ~6s, and
scores the brief against a hand-written list of what that day should have
contained. Run it before and after any selection change; `expected.yaml` states
human judgement and must never be edited to make a failing run pass.

Triage and adjudication verdicts are **recorded into the fixture**
(`triage.json`, `adjudication.json`) and replayed by `RecordedTriage` /
`RecordedAdjudicator`, exactly as `embeddings.npz` is. Without that the harness
would measure a selection path production no longer uses. `baseline_recall` is
**1.0** as of 2026-08-24; raise it as selection improves, never lower it.

**The default offline golden day does not cover story analysis.** That pass
needs the network, so `enable_story_analysis_llm` is tied to `live_editorial`:
only `--live-editorial` exercises it, and it reports the five counters rather
than gating. Every offline run prints a NOTE saying so. Until 2026-08-27 the
harness never set the flag at all while production defaulted it *on*, so a
green run said nothing whatever about a feature whose validators did not work.
Do not read an offline pass as evidence about story analysis.

Capture a new day with `python scripts/capture_golden_day.py` (40/source by
default — 15 is too thin for corroboration to mean anything).

## Story analysis — the guards are the hard part

`SAAF_ENABLE_STORY_ANALYSIS_LLM` is **on**, but it was switched off first and
only turned back on against measurements. Its env default used to be `"1"`
while `PipelineConfig.enable_story_analysis_llm` was `False`, which is how a
broken validator layer ran in production and in no test.

The output was never the problem; the guards were. Three of them, all fixed on
2026-08-27 and all now tested:

- **Numbers canonicalise to their magnitude, currency marker dropped.**
  `Rs22bn`, `Rs 22 billion` and `22 billion rupees` are one token, `22bn`. The
  old pattern required a word boundary before the first digit, so `Rs22bn`
  produced *no* token and `Rs483,036` produced `036` — meaning a fabricated
  rupee figure validated against a source with no money in it, and `Rs912,036`
  validated `Rs483,036`. A source `YYYY-YY` range expands to both endpoints on
  the **source side only**; the output side stays strict.
- **Related context needs a core anchor, not a shared name.** An anchor must
  appear in at least half the primary headlines, and the candidate must clear
  `_RELATED_MIN_SIMILARITY` (0.86). Similarity alone cannot do this job: on the
  live window the PIMS Rs22bn report the analysis genuinely needs sits at
  0.873, *below* junk at 0.88–0.91. `story_tags` are category labels and must
  never feed the anchor set — `Economy` is what matched an Uzbekistan/SCO
  report onto the gas-subsidy card.
- **A question must add a particular, not name the story.** "Why do such
  tragedies keep happening in PIMS?" names only the subject. A single word from
  the accountability-term list is not enough either — that is exactly how the
  prompt's own canonical BAD example passed.

Two rules about severity: the question's proper nouns are checked against the
**whole supplied input**, not the articles the model happened to cite (scoping
it to the subset rejected 40% of live questions); and
`unknown_publisher_in_analysis` is **recorded, never fatal** — every fact is
still validated, and discarding the analysis costs the reader the whole card
body. Rejected copy is persisted under `story_analysis.rejected`, which both
API routes strip before the DTO. `/api/feed` carries no `story_analysis` at all.

## Commands

Backend (from `backend/`):

```bash
source venv/bin/activate && python -m pytest -q
```

```bash
source venv/bin/activate && python run_pipeline.py --log-level INFO
```

```bash
source venv/bin/activate && python scripts/eval_golden_day.py
```

```bash
source venv/bin/activate && uvicorn main:app --reload
```

Frontend (from `frontend/`): `npm test`, `npm run dev`, `npm run build`.

## Rules of engagement

- **Verify claims against live output, not tests.** A green suite says the code
  does what it was written to do; it says nothing about whether the brief is
  good. Check `/api/feed`, the DB, and the rendered page.
- **Do not reintroduce a publish score.** The 21-term chain in
  `orchestrator.py` was deleted in Phase 4 because it saturated at 100 for
  every published card (I-4). Selection facts belong in `CandidateEvidence`,
  ordered lexicographically; judgement belongs to the editor. If a candidate is
  wrongly excluded, the log names the gate that did it.
- **Input pool before ranking.** If a story is missing from the brief, first ask
  whether it was ever ingested. Ranking fixes cannot recover an article that was
  never scraped (see `issues.md` I-1).
- **Never trust an HTTP 200 from a feed.** Two live endpoints serve well-formed
  feeds of ~9-month-old news. Always gate on the age of the newest item.
- **Re-run the research scripts rather than re-deriving.** `backend/scripts/research/`
  answers source-health questions in seconds; see `ingestion-research.md`.
- **A provider failure must be visible, not fatal.** A missing `GEMINI_API_KEY`
  used to raise straight out of `embed_articles` and kill the run, so `/health`
  had nothing to report and only looked wrong 28 hours later when the heartbeat
  went stale. `embedding_status`, `triage_status` and `editorial_status` all
  now reach `/health` and all three make the status `degraded`.
- **Do not let the UI assert more than the backend knows.** No invented
  freshness, confidence, or source counts. Equally, **do not let the UI quietly
  show less** — a render-time filter over a backend contract gap shrinks the
  brief silently (I-7). Fail loudly instead.
- **The entrypoints are not covered by imports.** `run_pipeline.py` and
  `main.py` are executed, never imported, so a syntax error there passes the
  whole suite. A live run is the only proof the pipeline starts.
- **Both suites and both linters run in CI** (`.github/workflows/ci.yml`), and
  the scheduled pipeline (`daily_pipeline.yml`) fails when any LLM stage is not
  `ok`. That workflow runs on a temporary GitHub
  runner against Supabase. Draft rows stay unpublished until validation and an
  atomic `publish_brief` RPC succeed; shared `pipeline_state` reaches Render.
  The backup can reuse validated drafts without new editorial calls. Embedding
  and triage health is reconciled against persisted rows after backfill, and
  recent cluster replacement and processing writes use transactions. Install
  the current Supabase schema before releasing the workflow. Scheduling still
  requires `ENABLE_DAILY_PIPELINE=true` after the first hosted test.
- **`degraded_sources` means "yielded nothing usable", not "nothing new".** It
  used to test inserted rows, so a second run in the same hour marked all eight
  sources degraded. `source_discovered_counts` records the usable count next to
  the inserted one.
- The worktree is frequently dirty with the user's own in-progress edits. **Do
  not revert or "clean up" unrelated modified files.**
- **Keep root docs to README, AGENTS and CLAUDE**. Supporting documentation
  belongs in `docs/`, which stays local; anything the README references belongs
  in `assets/`. Update `docs/status.md` after meaningful work rather than
  adding a new dated note; the note directories were deleted for exactly that
  reason. Scratch belongs outside the repo.

## Supporting scripts


Re-runnable evidence behind the ingest design described in `CLAUDE.md`.
None of these are part of the pipeline — they exist so source-health and
coverage claims can be re-checked rather than assumed.

Run from `backend/` with the venv active:

```bash
source venv/bin/activate && python scripts/research/probe_feeds.py
```

| Script | What it answers |
|---|---|
| `feeds_catalog.py` | Candidate feed list (data, not a script) |
| `probe_feeds.py` | Which feeds respond, parse, and are fresh. **Run this first when a source looks wrong.** |
| `compare_rss_vs_fetch.py` | Is RSS body text as good as fetching + extracting the page? |
| `test_fetch_reliability.py` | Per-publisher failure rate of direct article fetching |
| `test_coverage.py` | Do feeds miss URLs the site's section pages show? |
| `test_coverage_recency.py` | Are those missed URLs actually today's news? |
| `test_hotnews_recall.py` | Recall vs Google News Pakistan (raw — noisy) |
| `test_hotnews_recall2.py` | Recall vs Pakistani outlets only (the honest benchmark) |
| `test_combined_recall.py` | Does RSS + sitemap close the coverage gap? |
| `discover_feeds.py` | Find working feeds for publishers we don't ingest |
| `test_sitemaps.py` | Which publishers expose Google-News sitemaps |
| `trace_misses.py` | Where do genuinely-missed stories live? |
| `dawn_deep.py` | Dawn's full discovery surface |
| `prototype_ingest.py` | **Reference implementation** of the proposed design, end to end |

Outputs (`*.json`) are snapshots of a single run and are gitignored.

Be considerate: `prototype_ingest.py` issues ~28 requests per run. Avoid tight
loops against publisher sites, and keep a real User-Agent set.
