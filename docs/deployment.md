# Deploy Saaf Baat

Vercel hosts the website. Render hosts the read-only FastAPI endpoints. GitHub Actions runs the Python news pipeline, and Supabase stores the results. Visitors never trigger AI generation.

**Current state:** Supabase is connected and its schema is applied and verified (project `ayjimcicmtjwenvldmvm`, 2026-09-10). Vercel, Render and the GitHub Actions secrets are not yet configured, and no end-to-end hosted run has been verified. Render Free sleeps after idling and takes about a minute to wake, so the website serves the brief from Vercel's cache rather than calling Render on each visit — a reader gets the page immediately whether or not the API is awake. A request that does reach a waking backend is given 25 seconds before it is abandoned.

## 1. Create Supabase

Create a project dedicated to Saaf Baat. Keep the database password in your password manager. In its SQL editor, run [`backend/src/db/schema.sql`](../backend/src/db/schema.sql). The script is repeatable and preserves existing rows; it also removes the old cascading feed/cluster relation, enables RLS and denies anonymous/authenticated table access.

**Re-running it on a database an older copy of the file created is not automatically enough.** `CREATE TABLE IF NOT EXISTS` is a no-op on an existing table and skips its `CONSTRAINT` clauses with it, so the script reports success while leaving the table without its CHECKs and without the `UNIQUE` on `raw_articles.content_hash` that is the article dedup guarantee. The live project was in exactly that state until 2026-09-10. The file now ends with a backfill block that adds any missing constraint, so a re-run repairs this — but verify rather than assume, with the query below.

Verify by querying, not by trusting a green run. All four tables should report `rls_enabled=true`; `anon` and `authenticated` should hold zero table grants and no EXECUTE on the RPC:

```sql
SELECT c.relname, c.relrowsecurity AS rls_enabled,
       (SELECT count(*) FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype IN ('c','u')) AS constraints
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('raw_articles','clusters','analyzed_feed','pipeline_state');

SELECT r.rolname,
       has_function_privilege(r.rolname,'public.publish_brief(text,integer,jsonb)','EXECUTE') AS can_publish,
       (SELECT count(*) FROM information_schema.role_table_grants g
         WHERE g.grantee = r.rolname AND g.table_schema = 'public'
           AND g.table_name IN ('raw_articles','clusters','analyzed_feed','pipeline_state')) AS table_grants
FROM pg_roles r WHERE r.rolname IN ('anon','authenticated','service_role');
```

Then run the project's database linter (Advisors → Security). Four `rls_enabled_no_policy` notices at INFO are the intended design: RLS denies everything and only the server key, which bypasses it, has grants. One `extension_in_public` warning for `vector` is accepted — relocating the extension would rewrite the embedding column types for no security gain on a database with no public role access.

Copy the **project URL** and a **server secret key** (or legacy `service_role` key) from the project's API settings. The app calls it `SUPABASE_KEY`. Do not use the publishable/anon key: this deployment intentionally has no public database policies.

Enter keys directly into the dashboards below. Never put them in Git, README screenshots, a browser bundle, or a `NEXT_PUBLIC_` variable. Render currently needs a server key for its existing database client; its public API exposes only GET routes and filtered story DTOs. This key is privileged, so keep access to the Render account restricted. No Supabase key goes to Vercel.

## 2. Connect Vercel

Import `SaqlainXoas/saaf-baat` from GitHub. Choose **Root Directory: `frontend`**, framework **Next.js**, Node **22.x**. Build settings are in [`frontend/vercel.json`](../frontend/vercel.json).

Create the project to obtain its stable production `https://…vercel.app` domain. A first deployment may show the unavailable state until the backend is configured. Vercel Hobby is for eligible personal, non-commercial use.

## 3. Connect Render

Choose **New → Blueprint**, connect the same repository, and select the root [`render.yaml`](../render.yaml). It creates the `saaf-baat-api` Python web service on the Free plan.

Fill the prompted values:

| Render environment variable | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your server secret / legacy service-role key |
| `BACKEND_CORS_ALLOW_ORIGINS` | The exact stable Vercel URL, with `https://` and no trailing slash |

The Blueprint sets Python 3.11.14, production mode and `SAAF_DB_BACKEND=supabase`. It installs only `requirements-api.lock` and starts `uvicorn main:app --host 0.0.0.0 --port $PORT`. Do not add Gemini credentials or run the pipeline on this service. No persistent Render disk is needed because data lives in Supabase.

The Blueprint uses `/` for process liveness. `/health` reports database and editorial freshness separately; monitor its JSON `status`, not HTTP status alone. A not-yet-published database is expected to report degraded.

## 4. Finish Vercel configuration

Set these in the Vercel project's Production environment, then redeploy:

| Vercel environment variable | Value |
|---|---|
| `BACKEND_API_BASE_URL` | Your Render URL, e.g. `https://saaf-baat-api-….onrender.com` |
| `NEXT_PUBLIC_STRICT_LIVE_DATA` | `1` |
| `NEXT_PUBLIC_SITE_URL` | Your stable Vercel URL, e.g. `https://saaf-baat.vercel.app` |
| `REVALIDATE_SECRET` | A long random string you invent; use the same value for the `SAAF_REVALIDATE_SECRET` GitHub secret in step 5 |

Do not put localhost in hosted configuration. Without `NEXT_PUBLIC_SITE_URL` the page metadata and `robots.txt` fall back to `http://localhost:3000`, which would ship localhost URLs in the production page head.

The brief and story pages are served from Vercel's cache, not re-fetched per visitor, so a reader never waits on a sleeping Render instance and a backend outage shows the last good edition instead of an error. `REVALIDATE_SECRET` is what lets the pipeline swap that cache the moment a new edition publishes; the route fails closed without it, and a missed ping only costs freshness until the 15-minute window lapses.

Because the pages are prerendered, a Vercel build that runs while Render is unreachable bakes the unavailable state into the deployment, and it stays until something revalidates. Wake Render (open its `/health`) before triggering the Vercel deploy. If you do ship a deploy that shows the unavailable state, the next pipeline run's revalidation replaces it; redeploy to fix it sooner.

If `BACKEND_API_BASE_URL` is missing, the frontend silently falls back to `https://$VERCEL_URL/api`, which has no such routes. The symptom is a 404 "Unable to load brief", not an obvious configuration error — check this variable first when the site cannot load a brief.

For previews, configure these variables in Preview too, or expect the explicit unavailable state. Add only intended frontend origins to Render CORS; do not use `*`.

## 5. Connect the daily pipeline

In GitHub → repository **Settings → Secrets and variables → Actions**, create these repository secrets:

| GitHub secret | Value |
|---|---|
| `SUPABASE_URL` | The same project URL |
| `SUPABASE_KEY` | Server secret / service-role key; preferably a separate revocable server key for this worker |
| `GEMINI_API_KEY` | Your Gemini key with the required models enabled and an appropriate budget/quota |
| `SAAF_REVALIDATE_URL` | `https://<your-vercel-domain>/api/revalidate` |
| `SAAF_REVALIDATE_SECRET` | The same value as Vercel's `REVALIDATE_SECRET` |

Open **Actions → Publish morning brief → Run workflow**. It installs the locked pipeline dependencies and official spaCy English model, generates private draft cards, checks the run, and promotes the edition in a single database transaction. Failed generation or validation leaves the previous published edition standing. A shorter grounded edition is allowed after the editorial retries; a zero-card edition is never promoted.

Once the first run and public reader flow pass, create the **repository variable** `ENABLE_DAILY_PIPELINE=true`. This deliberate setup switch prevents unconfigured scheduled runs. The schedule starts at **06:17 Pakistan time**, allowing generation time before the morning. It is best-effort, not a guaranteed completion time. The workflow must exist on the repository's default branch for scheduling.

Enable GitHub Actions failure notifications for yourself. This repository is private, so scheduled runs draw on the account's included Actions minutes rather than the free public-runner pool — one pipeline run per day, and worth watching against the allowance. (The 60-day inactivity rule that disables schedules applies to public repositories, not this one.) Model quotas and provider storage/bandwidth limits remain separate.

## 6. Verify before sharing

0. Know what the database already holds. It carries a 2026-05-14 run — 180 articles, 23 clusters and 7 published cards — and those cards predate `metadata.brief_run_at`, so they carry no stamp. `_latest_brief_only` discards empty stamps and, finding none at all, returns every row, which means `/api/feed` serves that four-month-old 7-card brief until the first pipeline run. This is the expected pre-run state, not a misconfiguration, and the first real edition outranks those rows and filters them out permanently. Do not delete them first: the `preserve_published_context` trigger protects the last published edition on purpose, and clearing it before a run that might publish nothing leaves the reader with no brief at all.
1. Wait for Render's initial build to finish. Open `/health` and check `database: connected`.
2. Run the GitHub workflow once. Check its publication step and uploaded heartbeat; do not treat a green install step as a published edition.
3. Open Render `/api/feed`: confirm a fresh timestamp and a distinct, meaningful edition. Open each returned `story_id` at `/api/stories/{story_id}`.
4. Open the Vercel site on your phone, read a story, follow its publisher link, return, switch theme, and reach the end. Check no localhost links or internal errors appear.
5. Leave Render idle for twenty minutes, then load the site. The brief must still appear immediately, served from cache. If it shows the retry state instead, the page is not actually cached — check that the publish step reported a revalidation and that `REVALIDATE_SECRET` matches on both sides.
6. Keep the stable public URL for your LinkedIn post only after these checks pass.

The RPC keeps publication atomic; it does not prove editorial quality. Review several consecutive days and monitor failures. Back up Supabase and test restoration. Watch database size: the pipeline prunes after seven days, while database guards retain the last published edition and source context still referenced by published stories. Free storage is limited. A recurring verified backup and restore process is still operational work before a dependable long-term launch.

## 7. Add your own domain

Optional, and best done after step 6 passes on the `.vercel.app` URL.

Point the domain at **Vercel only**. The browser never calls Render directly — Next fetches the API server-side — so the API can keep its `.onrender.com` address and needs no domain, no DNS record and no certificate of its own.

In Vercel → project → **Settings → Domains**, add both the apex (`example.com`) and `www`. Vercel then shows the exact records to create at Namecheap or Name.com; use the values Vercel gives you rather than any copied from elsewhere, since they differ per project:

| Host | Type | Points to |
|---|---|---|
| `@` | `A` | The apex IP Vercel displays |
| `www` | `CNAME` | The `…vercel-dns.com` target Vercel displays |

At **Namecheap** these go under Domain List → Manage → Advanced DNS, and the domain must be on *Namecheap BasicDNS*, not a parking page or a third-party nameserver. At **Name.com** they are under Manage → DNS Records. Delete any pre-existing parking `A` or `CNAME` record on the same host first, or the new one will not resolve. Propagation is usually minutes; Vercel issues the certificate automatically once it sees the records.

Pick one of the two as the canonical domain in Vercel and let it redirect the other, so a story is not served under two URLs.

Then update three values to the new origin and redeploy:

| Where | Variable | New value |
|---|---|---|
| Vercel | `NEXT_PUBLIC_SITE_URL` | `https://example.com` — otherwise page metadata and `robots.txt` keep advertising the `.vercel.app` host |
| GitHub secret | `SAAF_REVALIDATE_URL` | `https://example.com/api/revalidate` |
| Render | `BACKEND_CORS_ALLOW_ORIGINS` | Add the new origin (comma-separated, `https://`, no trailing slash) |

The Render value matters least — nothing in the browser calls that API today — but leaving it correct keeps the service honest if anything ever does, and an empty or `*` value makes it refuse to boot in production.

Check afterwards that the site loads on the domain, that a published story page loads directly (not only via the home page), and that `SAAF_REVALIDATE_URL` still returns `{"ok":true}` on the next pipeline run.

## Local validation and maintenance

```bash
cd backend
source venv/bin/activate
python -m pytest -q
python scripts/eval_golden_day.py
```

```bash
cd frontend
npm test
npm run lint
npm run build
```

Runtime lockfiles are generated from `requirements-api.in` and `requirements-pipeline.in` using `uv pip compile … --python-version 3.11`. Regenerate, audit and test them together when updating dependencies. The Render API deliberately does not install spaCy, NumPy, scraping libraries or model SDKs.

## Provider references

- [Render Blueprint settings](https://render.com/docs/blueprint-spec) and [Free service limits](https://render.com/docs/free)
- [Supabase server keys](https://supabase.com/docs/guides/getting-started/api-keys) and [pricing/quotas](https://supabase.com/pricing)
- [Vercel Hobby eligibility](https://vercel.com/docs/plans/hobby)
- [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Vercel custom domains](https://vercel.com/docs/domains/working-with-domains/add-a-domain)
