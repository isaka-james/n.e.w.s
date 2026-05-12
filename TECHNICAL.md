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
2. **Triage** — DeepSeek assigns each article a compass layer (N/E/W/S) and a 0-1 relevance score.
3. **Boost** — thin layers trigger a targeted re-fetch from Guardian and NYTimes.
4. **Write** — DeepSeek reasoner writes the briefing.
5. **Cache** — stored in PostgreSQL. Re-run with cached articles (AI only) or fresh fetch (From scratch).

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

