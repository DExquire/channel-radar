# CLAUDE.md — working agreements for this repo

Conventions and layer boundaries for an agent editing this project. Not a repeat
of the README (which explains *what* and *why* to a human).

## Layer boundaries (dependencies point downward only)

```
web (FastAPI routes, templates)      ← HTTP + HTML only, no business logic
  └─ services (channel_service, collector, dashboard, ai, analytics, parser)
       └─ repositories (channel_repo, post_repo)   ← all SQL lives here
            └─ models (SQLAlchemy ORM) + db (engine/session)
```

Rules:
- **Routes** never touch the ORM session directly except via `Depends(get_db)`, and
  never build queries — they call a service.
- **Services** hold orchestration/business rules. They call repositories for data,
  never write raw SQL.
- **Repositories** own every `select()/insert`. If you need a new query, add a
  function here, don't inline it in a service.
- **`parser.py` and `analytics.py` are PURE** — no I/O, no DB, no network. Keep
  them that way; they are the unit-tested core. New parsing/metric logic goes here
  and gets a fixture-based test.
- **`ai.py` must never raise to its callers.** Every path returns a usable value or
  `None`. If you add an AI call, wrap failures and add a mocked test.

## Idempotency (do not break)
Collection must stay idempotent. Posts are keyed by `UNIQUE(channel_id, tg_msg_id)`;
metrics are **append-only**. Never "update the latest metric in place" — append a
new snapshot. `tests/test_collector_idempotency.py` guards this.

## Secrets
No secrets in git. Everything sensitive is an env var (see `.env.example`).
`.env` and `*.db` are gitignored.

## Tests
`pytest`, **offline**: no real network, no real LLM (mock `ai._generate` or
`collector.fetch_channel_html`). Add a test with any parser/analytics/idempotency
change. Run: `pytest -q`.

## Collection model
Two drivers, same code path (`channel_service.collect_all_due`):
- external cron → `POST /api/cron/collect` (Render; service sleeps),
- in-process APScheduler when `RUN_SCHEDULER=1` (always-on hosts).
Adding a channel runs exactly one synchronous cycle so the user sees data fast;
heavy AI work stays off that path.
