# Technical Reference

## Stack

| | |
|---|---|
| Backend | FastAPI, SQLModel, PostgreSQL, Alembic |
| Frontend | Next.js, Tailwind CSS |
| AI | DeepSeek (`deepseek-chat` triage, `deepseek-reasoner` writing) |
| Orchestration | Docker Compose |
| Proxy | Nginx |

## Briefing pipeline

1. **Fetch** — all sources in parallel. Articles older than 3 days dropped at the API level where supported, otherwise post-fetch.
2. **Triage** — DeepSeek assigns each article a compass layer (N/E/W/S) and a 0–1 relevance score.
3. **Boost** — if the city (N) or country (E) layer is empty, a single targeted re-fetch from Guardian and NYTimes runs.
4. **Bucket (Python)** — articles are grouped into N/E/W/S buckets, blocked-word matches dropped, each bucket sorted by score, and capped at the user's per-layer target. The writer never sees more than this — so no layer can be accidentally emptied.
5. **Write** — DeepSeek rewrites each pre-bucketed article (headline, hook, summary, tone) and adds the report-level prose. It does not filter, classify, or re-rank.
6. **Cache** — stored in PostgreSQL. Re-run with cached articles (AI only) or fresh fetch (From scratch).

## Compass layers

| | |
|---|---|
| N | City |
| E | Country |
| W | Continent |
| S | World |

## News sources

| Source | Daily limit | Rate limit | Date filter |
|---|---|---|---|
| NewsData.io | 200 req/day | none | post-fetch |
| NewsAPI | 100 req/day | none | `from` |
| NewsCatcher CatchAll | pay-as-you-go | 1 concurrent job | `DISCOVERY_WINDOW_DAYS = 1` |
| GNews | 100 req/day | 1 req/s | `from` |
| The Guardian | 500 req/day | 1 req/s | `from-date` |
| New York Times | 4,000 req/day | 10 req/min | `begin_date` |

Rate limits are enforced in-process with a `threading.Lock` throttle.

## NewsCatcher CatchAll

Asynchronous pipeline (submit → analyzing → fetching → clustering → completed).

1. **Reuse** — completed job within last 23 h, use cached records.
2. **Resume** — job running, poll up to 3 min.
3. **Submit** — no job, submit new `lite` job with `DISCOVERY_WINDOW_DAYS = 1`.

## Migrations

Applied automatically on startup. To run manually:

```bash
docker compose exec backend alembic upgrade head
```

## Project structure

```
backend/
  fetcher.py        fetch_stories(), fetch_local_boost()
  deepseek.py       triage + writing prompts
  routers/          auth, reports, users
  alembic/          migrations
frontend/
  app/              pages
  components/       UI
  lib/              API client, contexts
nginx/              proxy config
```

