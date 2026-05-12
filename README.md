# N.E.W.S.

Your personal AI news assistant. Tell it where you live and what you care about — it fetches today's headlines and writes you a clean daily briefing, every day.

![N.E.W.S. dashboard](img/home-not-generated.png)

---

## Before you start

You'll need two things installed on your computer:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the whole app, no other installs needed
- A terminal (Terminal on Mac/Linux, Command Prompt or PowerShell on Windows)

---

## Step 1 — Get the code

```bash
git clone https://github.com/isaka-james/n.e.w.s
cd n.e.w.s
```

---

## Step 2 — Create your config file

```bash
cp .env.example .env
```

Now open the `.env` file you just created in any text editor and fill in your API keys. You need to sign up for free accounts at each of these — it takes about 10 minutes total:

| Key in the file | Where to get it | Free tier |
|---|---|---|
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com | Pay-as-you-go, very cheap |
| `NEWSDATA_API_KEY` | https://newsdata.io/register | 200 requests/day |
| `NEWSAPI_API_KEY` | https://newsapi.org/register | 100 requests/day |
| `NEWSCATCHER_API_KEY` | https://www.newscatcherapi.com | Pay-as-you-go |
| `GNEWS_API_KEY` | https://gnews.io/signup | 100 requests/day |
| `GUARDIAN_API_KEY` | https://open-platform.theguardian.com/access/ | 500 requests/day |
| `NYTIMES_API_KEY` | https://developer.nytimes.com/accounts/create | 4000 requests/day |

You also need to set a secret key for logins. Run this command and paste the output as `JWT_SECRET_KEY`:

```bash
openssl rand -hex 32
```

The database section at the bottom of `.env` can stay as-is.

---

## Step 3 — Run it

```bash
docker compose up -d --build
```

Wait about 30 seconds for everything to start, then open **http://localhost:4291** in your browser.

Register an account, set your city, country and topics, then press **Generate today's report**.

---

## Stopping it

```bash
docker compose down
```

---

## Screenshots

See [img/README.md](img/README.md) for a tour of every screen.

---

## Technical docs

For stack details, architecture, and how the briefing pipeline works see [TECHNICAL.md](TECHNICAL.md).

---

## License

MIT. See [LICENSE](LICENSE).

Built by [Isaka James](https://github.com/isaka-james).
