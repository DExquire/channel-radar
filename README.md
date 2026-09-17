# channel-radar

Live analytics dashboard for public Telegram channels. Collects posts from the
anonymous web preview (`t.me/s/<channel>` — **no Bot API, no keys**), stores them
with their metric dynamics, analyzes them with an LLM, and serves a dashboard you
can open in a browser at any time.

## 🔗 Live service

**https://REPLACE-ME.onrender.com**  ← _(fill in after deploy — see “Deploy” below)_

> Render's free tier sleeps when idle; the very first request after a quiet period
> can take ~30–50 s to wake. Open the link, give it a moment, and it’s responsive.

---

## What it does

- **Add a channel from the UI.** Type `@durov`, press *Add* — the first collection
  runs synchronously and you see posts within seconds. Missing/private channels are
  added with a clear "unavailable" state instead of failing.
- **Incremental, idempotent collection.** Re-collecting never duplicates posts
  (natural key `channel_id + tg_msg_id`); each run appends a metric snapshot, so
  view/reaction/subscriber **dynamics** are preserved, not just the latest value.
- **Dashboard.** Overview (subscribers, post count, last-collected, source health);
  channel page (subscriber trend chart, post list with views/reactions, period
  filter, AI digest, spike flags); per-post page (metric history over time, link to
  original).
- **AI layer (Gemini).** Per-period channel digest + per-post category. Anomaly
  ("sharp spike vs usual") is a deterministic z-score. If the LLM has no key or hits
  its limit, the dashboard keeps working and shows "AI unavailable".

## Architecture

Layered, dependencies point downward (details in `CLAUDE.md`):

```
web (FastAPI + Jinja2)  →  services  →  repositories  →  models/db
```

- `services/parser.py` — **pure** HTML → dataclasses (unit-tested on fixtures).
- `services/collector.py` — fetch (httpx) + **idempotent** upsert; `ingest()` is
  pure-DB and directly tested.
- `services/analytics.py` — **pure** metric arithmetic + anomaly z-score.
- `services/ai.py` — Gemini over REST, never raises, always degrades gracefully.
- `services/channel_service.py` — orchestration (add channel, collect-all, digests).
- `repositories/*` — all SQL.

### Data model (see `docs/adr/0002`)
`channels` (unique `username`) · `posts` (unique `channel_id,tg_msg_id`) ·
`post_metrics` (append-only) · `channel_metrics` (append-only) · `channel_digests`
(cached AI). Identity is separate from measurements — that's what stores dynamics.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optionally add GEMINI_API_KEY
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```
Defaults to SQLite, so it runs with zero external setup. Add a channel in the UI,
or trigger a collection cycle manually:
```bash
curl -X POST localhost:8000/api/cron/collect
```

## Tests

```bash
pytest -q
```
Offline by design: no network, no real LLM (AI calls and HTTP fetch are mocked).
They cover the risk areas — parser normalization on fixtures, collection
idempotency + snapshot accumulation, analytics arithmetic, and AI graceful
degradation (including a simulated 429).

## Deploy (Render + Neon)

1. **Neon** — create a free Postgres project, copy the connection string
   (`postgresql+psycopg://...?sslmode=require`).
2. **GitHub** — push this repo.
3. **Render** — New ▸ Blueprint ▸ pick the repo (`render.yaml` is detected). After
   the first deploy, set env vars in the dashboard:
   - `DATABASE_URL` = the Neon string
   - `GEMINI_API_KEY` = key from https://aistudio.google.com/app/apikey
   - `CRON_SECRET` = any random string
4. **Keep-alive + background collection** — add repo secrets `SERVICE_URL`
   (your Render URL) and `CRON_SECRET` (same value); the included GitHub Action
   (`.github/workflows/collect.yml`) hits `/api/cron/collect` every 30 min, which
   wakes the service and runs the incremental refresh.
5. Put the Render URL at the top of this README.

Hosting trade-offs and why this combo → `docs/adr/0001-hosting.md`.
Switching to Fly.io (no cold start) is config-only (`RUN_SCHEDULER=1`), no code
change.

## AI: what and why (see `docs/adr/0003`)
Gemini `gemini-2.0-flash` (free, no card). Digest = "what the channel wrote about
this period" (cached per channel/period); category = short topic label per post
(background, quota-capped). **If the LLM is unavailable or rate-limited**, digests
return `None` ("unavailable" in the UI) and categories fall back to a keyword
heuristic — collection and the rest of the dashboard are unaffected.

## Not done / scope notes
- **No auth** (public link, per task).
- **Reactions/forwards** aren't always exposed in the anonymous web preview; when
  absent they're stored as 0. **Views** and text/date/id are the reliable core.
- No comparison-of-multiple-channels chart or "not posted in 3 days" alert yet
  (source health already flags stale/down); both are small additions on this model.
- Test coverage targets risk, not 100%.

## Reused from the earlier `telegram-Godbot`
Patterns carried over: SQLAlchemy models, idempotent upsert (its `INSERT OR IGNORE`
→ a real unique constraint), loguru logging, scheduled refresh, theme/category
idea. Its collection used **Telethon + API_ID/API_HASH**, which this task forbids
(anonymous web preview only) and which can't deploy cleanly, so collection here is
implemented against `t.me/s`. That project had **no** LLM code, so the AI layer is
new (`docs/adr/0003`).
