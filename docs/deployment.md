# Deploy Saaf Baat

Vercel hosts the website. Render hosts the read-only FastAPI endpoints. GitHub Actions runs the Python news pipeline, and Supabase stores the results. Visitors never trigger AI generation.

**Current state:** configuration is prepared locally; no provider accounts are connected and no hosted deployment has been verified. Render Free sleeps after idling and takes about a minute to wake, so the website serves the brief from Vercel's cache rather than calling Render on each visit — a reader gets the page immediately whether or not the API is awake. A request that does reach a waking backend is given 25 seconds before it is abandoned.

## 1. Create Supabase

Create a project dedicated to Saaf Baat. Keep the database password in your password manager. In its SQL editor, run [`backend/src/db/schema.sql`](../backend/src/db/schema.sql). The script is repeatable and preserves existing rows; it also removes the old cascading feed/cluster relation, enables RLS and denies anonymous/authenticated table access.

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

Enable GitHub Actions failure notifications for yourself. Public repository schedules may be disabled after 60 days of inactivity. Standard public runners are free; private repositories have an allowance. Model quotas and provider storage/bandwidth limits remain separate.

## 6. Verify before sharing

1. Wait for Render's initial build to finish. Open `/health` and check `database: connected`.
2. Run the GitHub workflow once. Check its publication step and uploaded heartbeat; do not treat a green install step as a published edition.
3. Open Render `/api/feed`: confirm a fresh timestamp and a distinct, meaningful edition. Open each returned `story_id` at `/api/stories/{story_id}`.
4. Open the Vercel site on your phone, read a story, follow its publisher link, return, switch theme, and reach the end. Check no localhost links or internal errors appear.
5. Leave Render idle for twenty minutes, then load the site. The brief must still appear immediately, served from cache. If it shows the retry state instead, the page is not actually cached — check that the publish step reported a revalidation and that `REVALIDATE_SECRET` matches on both sides.
6. Keep the stable public URL for your LinkedIn post only after these checks pass.

The RPC keeps publication atomic; it does not prove editorial quality. Review several consecutive days and monitor failures. Back up Supabase and test restoration. Watch database size: the pipeline prunes after seven days, while database guards retain the last published edition and source context still referenced by published stories. Free storage is limited. A recurring verified backup and restore process is still operational work before a dependable long-term launch.

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
