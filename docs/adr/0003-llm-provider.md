# ADR 0003 — LLM provider: Google Gemini, with graceful degradation

## Status
Accepted.

## Context
The AI layer is mandatory and must be *useful*, on a free tier, with the key kept
out of git, and the dashboard must not fall over if the LLM is down or rate-limited.

## Decision
Use **Google Gemini** (`gemini-3.6-flash`) via the AI Studio free tier, called over
plain **httpx REST** (no heavy SDK). Two features:
- **Channel digest** — "what did this channel write about in the last N days",
  cached per `(channel, period)` in `channel_digests` so we don't re-call per view.
- **Post categorization** — a short topic label per post, done in background
  collection runs, capped per run to respect the free quota.

Anomaly detection ("post sharply above the channel's usual") is done with a
deterministic **z-score** in `analytics.py`, *not* the LLM — it's cheaper, testable
and doesn't burn quota.

## Graceful degradation (the important part)
`app/services/ai.py` returns `None` (digest) or falls back to a keyword
categorizer (category) on **any** failure:
- no `GEMINI_API_KEY` configured,
- HTTP 429 (quota/limit),
- any network/parse error.
The dashboard then shows "AI digest unavailable" and keeps serving all collected
data. This is covered by tests (`tests/test_ai.py`), including a simulated 429.

## Why not the earlier project's setup
The provided `telegram-Godbot` had **no LLM integration** (its `requirements.txt`
and code contain none), so there was nothing to reuse there; its collection also
used Telethon with `API_ID/API_HASH`, which this task forbids. We kept its
*patterns* (SQLAlchemy models, idempotent upsert, loguru, scheduled refresh) and
added the AI layer fresh.

## Alternatives considered
- **Groq / OpenRouter free tiers** — equally viable; provider is isolated behind
  one module, so switching is a small change. Gemini chosen for the no-card key.
