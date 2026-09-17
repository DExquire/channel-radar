# ADR 0002 — Storing metric dynamics, not just the latest value

## Status
Accepted.

## Context
Views, reactions and subscriber counts change over time. The task explicitly
requires storing the *dynamics*, and requires idempotent collection with a
natural key so re-collection never duplicates data.

## Decision
Separate **identity** from **measurements**:

- **`channels`** — one row per channel. `username` is **UNIQUE** (natural key).
- **`posts`** — one row per post. **UNIQUE(channel_id, tg_msg_id)**; `tg_msg_id`
  is Telegram's own message id, the natural key. Re-parsing the same page matches
  the existing row instead of inserting.
- **`post_metrics`** — **append-only** snapshot `(post_id, views, forwards,
  reactions, collected_at)`. Every collection appends a row.
- **`channel_metrics`** — **append-only** snapshot `(channel_id, subscribers,
  post_count, collected_at)`.
- **`channel_digests`** — cached AI output per `(channel_id, period)`.

Idempotency is enforced at the **DB level** by the unique constraints, and in the
service layer by upsert-on-natural-key. This is the same guarantee the earlier
`telegram-Godbot` project got from `INSERT OR IGNORE`, expressed as a proper
constraint.

## Consequences
- Trends (subscriber growth, per-post view curve) come straight from the snapshot
  tables — the dashboard chart and the anomaly baseline both read them.
- Storage grows linearly with collections; fine for the "~dozen channels" scope.
  If it ever mattered, snapshots could be down-sampled (keep hourly, roll up daily)
  without touching identity tables.
- The latest value is cached on `channels.subscribers` / `posts` for cheap list
  views; the truth for history lives in the snapshot tables.

## Alternatives considered
- **Overwrite latest value only** — simplest, but loses all dynamics. Rejected:
  directly violates the requirement.
- **One wide row per post updated in place** — can't answer "views over time".
