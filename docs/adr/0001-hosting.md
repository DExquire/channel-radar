# ADR 0001 — Hosting: Render (web) + Neon (Postgres)

## Status
Accepted.

## Context
The service must be reachable at a public URL at review time, on a free tier, and
must keep collecting data on a schedule. Free tiers each have a catch (see the
task's table): sleeping services, 90-day databases, limited credits, required cards.

## Decision
- **Web service: Render.com free (Docker).**
- **Database: Neon.tech free Postgres**, kept *separate* from the app host.

## Consequences / limits and how we handle them
- **Render free sleeps after ~15 min idle** → the first request after sleep is
  slow (tens of seconds). We accept this and mitigate it: an external **GitHub
  Actions cron** (`.github/workflows/collect.yml`) hits `POST /api/cron/collect`
  every 30 min, which both **wakes** the service and **drives collection**. So an
  in-process scheduler is *not* relied upon on Render (`RUN_SCHEDULER=0`).
- **Render's own free Postgres expires after 90 days.** We deliberately use
  **Neon** instead, whose free Postgres is not time-boxed the same way, so the DB
  outlives the review window. The app is DB-agnostic (`DATABASE_URL`), so this is
  a config choice, not a code choice.
- **Cold start during review** → the cron keeps the instance warm most of the
  time; the README tells the reviewer to open the link a few seconds early.

## Alternatives considered
- **Fly.io + Neon**: always-on VM (no cold start) but needs manual Postgres/VM
  config. Chosen as the documented fallback — because the app is a plain Docker
  image driven by env vars, moving to Fly is a new deploy config + `RUN_SCHEDULER=1`,
  **no code change**.
- **Railway**: easy, but the starter credit can run out mid-review — rejected for a
  time-boxed evaluation.
- **Cloud Run**: generous, but requires a card on the account — avoided.
