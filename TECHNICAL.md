# Technical Reference

Architecture, pipeline details, and production deployment notes for N.E.W.S.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLModel, PostgreSQL, Alembic |
| Frontend | Next.js, Tailwind CSS |
| AI | DeepSeek (`deepseek-chat` for triage, `deepseek-reasoner` for writing) |
| Orchestration | Docker Compose |
| Reverse proxy | Nginx |

---

## How a briefing is built

1. **Fetch** — All enabled providers are called in parallel via `ThreadPoolExecutor`. Articles older than 3 days are dropped — either at the API level (Guardian `from-date`, NewsAPI `from`, NYTimes `begin_date`, GNews `from`) or post-fetch for sources without date filter params (NewsData `/latest`).

2. **Triage** — DeepSeek (`deepseek-chat`) scores every article: assigns it to a compass layer (N/E/W/S) and a 0–1 relevance score.

3. **Local boost** — If a geographic layer has fewer than 10 articles after triage, `fetch_local_boost` hits The Guardian and NYTimes again with larger page sizes for the user's city/country.

4. **Write** — DeepSeek (`deepseek-reasoner`) writes the final briefing: title, opening line, mood per layer, story cards, closing line.

5. **Cache** — The report is stored in PostgreSQL. Re-runs from the Advanced page can reuse the article cache ("AI only") or fetch fresh ("From scratch").

---

## News sources

| Source | Daily free limit | Rate limit | Date filter |
|---|---|---|---|
| NewsData.io | 200 req/day | — | post-fetch |
| NewsAPI | 100 req/day | — | `from` param |
| NewsCatcher CatchAll | pay-as-you-go | 1 concurrent job | `DISCOVERY_WINDOW_DAYS = 1` |
| GNews | 100 req/day | 1 req/s | `from` param |
| The Guardian | 500 req/day | 1 req/s | `from-date` param |
| New York Times | 4,000 req/day | 10 req/min | `begin_date` param (Article Search only) |

All 1 req/s limits are enforced in-process with a `threading.Lock` throttle — the same mechanism used in `gnews_fetcher.py` and `guardian_fetcher.py`.

---

## Compass layers

| Letter | Scope |
|---|---|
| **N** | Narrow — user's city |
| **E** | Expanded — user's country |
| **W** | Wide — user's continent |
| **S** | Sweeping — the world |

---

## NewsCatcher CatchAll

CatchAll is asynchronous (submit → analyzing → fetching → clustering → enriching → completed). Strategy:

1. **Reuse** — if a completed job exists for this user in the last 23 hours, use its cached records (no API call).
2. **Resume** — if a job is running, poll for up to 3 minutes. Use results if it finishes; otherwise proceed with what other sources returned.
3. **Submit** — if no job exists, submit a new `lite` job with `DISCOVERY_WINDOW_DAYS = 1` (keeps job time under 2 minutes vs. the default 10–15 min for a 5-day window).

---

## Database migrations

Migrations are applied automatically on backend startup via Alembic. To run manually inside the container:

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

---

## Production deployment

`docker-compose.yml` is the production stack:

- No bind mounts — images are self-contained
- Uvicorn runs with multiple workers
- `restart: always` on all services
- Nginx terminates HTTP and proxies to the backend and frontend

```bash
docker compose up -d --build
```

Configure your domain and TLS in `nginx/nginx.conf`.

---

## Project structure

```
backend/          FastAPI app, fetchers, DeepSeek integration
  fetcher.py      Main orchestrator — fetch_stories(), fetch_local_boost()
  deepseek.py     Triage and report-writing prompts
  routers/        Auth, reports, users endpoints
  alembic/        DB migrations
frontend/         Next.js app
  app/            Pages (dashboard, settings, advanced, login, register)
  components/     Shared UI components
  lib/            API client, auth context, notifications context
nginx/            Reverse proxy config
img/              Screenshots
```
