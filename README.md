# N.E.W.S.

A personal news institution. One briefing a day, written for you, across four layers: your city, your country, your continent, the world.

![N.E.W.S. dashboard](img/home-not-generated.png)

## What it does

N.E.W.S. fetches articles from six providers (NewsData, NewsAPI, NewsCatcher CatchAll, GNews, The Guardian, The New York Times), filters by your tags and blocked words, classifies each story into one of four geographic layers, and writes a single daily briefing using DeepSeek.

The four layers:

- **N** Narrow, your city
- **E** Expanded, your country
- **W** Wide, your continent
- **S** Sweeping, the world

You can pick a daily auto-generate time, or trigger generation manually from the dashboard.

## Stack

- Backend: FastAPI, SQLModel, PostgreSQL, Alembic
- Frontend: Next.js, Tailwind
- AI: DeepSeek (`deepseek-chat` for triage, `deepseek-reasoner` for writing)
- Orchestration: Docker Compose
- Reverse proxy: Nginx

## Run it locally

You need Docker and Docker Compose. No host installs of Python or Node are needed.

```
git clone https://github.com/isaka-james/n.e.w.s
cd n.e.w.s
cp .env.example .env
```

Edit `.env` and fill in your API keys (links in the file point to where each one is signed up).

Then:

```
docker compose -f docker-compose.dev.yml up -d
```

Open http://localhost:4291

Database migrations run automatically on backend start.

## Production

`docker-compose.yml` is the production stack (no bind mounts, multi-worker uvicorn, restart=always):

```
docker compose up -d --build
```

## How a briefing is built

1. The fetcher calls all enabled providers in parallel. NewsCatcher CatchAll runs asynchronously (submit, poll, pull) with a one-day discovery window so most jobs finish under two minutes.
2. DeepSeek triages every article: assigns N/E/W/S and a 0-1 relevance score.
3. If a geographic layer is thin, the fetcher hits Guardian and New York Times again for targeted local boost.
4. DeepSeek `reasoner` writes the final briefing: title, opening line, mood per layer, story cards, closing line.
5. The report is cached for the day. Re-runs from the Advanced page can re-use the same article cache or fetch fresh.

## Screenshots

See [`img/README.md`](img/README.md) for a walkthrough of every screen.

## License

MIT. See [LICENSE](LICENSE).

Built by [Isaka James](https://github.com/isaka-james).
