# Metadata import setup (step by step)

The **Import metadata** feature uses **[The Movie Database (TMDB)](https://www.themoviedb.org/)** — a free API for movie and TV descriptive data (genre, cast, synopsis, studio, etc.).

If you see **"Not Found"**, the UI cannot reach the metadata API. Follow every step below in order.

---

## Step 1 — Get a TMDB API key (free, ~2 minutes)

1. Go to **https://www.themoviedb.org/** and create an account (or log in).
2. Open **https://www.themoviedb.org/settings/api**
3. Click **Request an API Key**
4. Choose **Developer** (not commercial for personal/dev use).
5. Accept the terms and fill in the short application (app name: `Stream Catalog`, URL: `http://localhost` is fine).
6. On the next screen, open **API Key (v3 auth)** — copy the key (a long string, not the “API Read Access Token” label confusion — use the **v3 API Key**).

Keep this key private. Do not commit it to GitHub.

---

## Step 2 — Add the key to your backend `.env`

1. In Terminal:

```bash
cd /Users/brianchun/stream-catalog/backend
cp .env.example .env
```

2. Open `backend/.env` in a text editor.
3. Set:

```env
TMDB_API_KEY=paste_your_v3_api_key_here
SEED_ON_STARTUP=true
```

4. Save the file.

`.env` is gitignored — it will not be pushed to GitHub.

---

## Step 3 — Install backend dependencies

```bash
cd /Users/brianchun/stream-catalog/backend
source .venv/bin/activate
pip install -r requirements.txt
```

This installs `httpx`, which calls TMDB.

---

## Step 4 — Restart the API server (critical)

An old server process does **not** include `/metadata` routes. You must restart.

1. In the Terminal window running uvicorn, press **Ctrl+C** to stop it.
2. Start again:

```bash
cd /Users/brianchun/stream-catalog/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

3. Confirm metadata routes exist:

```bash
curl -s http://127.0.0.1:8000/openapi.json | grep metadata
```

You should see `/api/v1/metadata/search` in the output.

---

## Step 5 — Keep the frontend running

In a **second** Terminal window:

```bash
cd /Users/brianchun/stream-catalog/frontend
npm run dev
```

Open **http://localhost:5173** → **Titles** → **+ New title**.

---

## Step 6 — Test the connection

### A. Test TMDB key + API in Terminal

```bash
curl -s "http://127.0.0.1:8000/api/v1/metadata/search?q=gladiator&title_type=movie" | head -c 500
```

**Success:** JSON array with titles like `"Gladiator"`.

**If you see** `TMDB API key not configured` → fix Step 2 and restart Step 4.

**If you see** `{"detail":"Not Found"}` → backend not restarted (Step 4).

### B. Test in the UI

1. **+ New title**
2. Type `gladiator` in **Import metadata**
3. Click **Search**
4. Click a result (e.g. Gladiator 2000) — form fields should fill in.

---

## Step 7 — Push to GitHub / cloud (when ready)

| Where | What to set |
|--------|-------------|
| **GitHub** | Do **not** commit `.env` |
| **App Runner** (API) | Env var `TMDB_API_KEY` = your v3 key |
| **Amplify** (UI) | `VITE_API_URL` = your App Runner URL (no code change for TMDB — key stays on API only) |

Redeploy App Runner after adding `TMDB_API_KEY`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|--------|-----|
| **Not Found** | Old API process or API not running | Restart uvicorn (Step 4); check port 8000 |
| **TMDB API key not configured** | Missing `TMDB_API_KEY` in `.env` | Step 2 + restart |
| **Invalid TMDB API key** | Wrong key pasted | Copy v3 key again from TMDB settings |
| **No matches found** | Typo or type filter | Try `movie` type; search `Gladiator` |
| Search works in curl but not UI | Frontend not proxied to API | Run `npm run dev` (not `vite preview` alone without API) |
| CORS error in browser | API CORS missing UI origin | Add `http://localhost:5173` to `CORS_ORIGINS` in `.env` |

---

## What TMDB does *not* provide

- **Licensor** — enter manually (your rights holder / distributor).
- **Territories / availability** — catalog-specific; fill in after import.

---

## APIs you need (summary)

| API | Required? | Purpose |
|-----|------------|---------|
| **TMDB** | Yes, for metadata import | Search + descriptive metadata |
| **Your FastAPI backend** | Yes | Proxies TMDB, stores titles in your DB |
| OMDb / TVDB | No (future) | Not implemented yet |

You only need **one external API key today: TMDB**.
