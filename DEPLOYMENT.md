# Deploy Stream Catalog (GitHub + Amplify + AWS)

Amplify hosts the **React admin UI**. The **FastAPI API** runs on **AWS App Runner** (Amplify does not run Python APIs). Both connect to the same **PostgreSQL** database so your catalog persists and is reachable from any computer.

```
GitHub repo
    ├── Amplify Hosting  →  https://main.xxxxx.amplifyapp.com  (frontend)
    └── App Runner       →  https://xxxxx.awsapprunner.com       (API)
              │
              └── Neon / RDS PostgreSQL (shared data)
```

---

## 1. Push the project to GitHub

```bash
cd /Users/brianchun/stream-catalog
git init
git add .
git commit -m "Initial Stream Catalog — TM + MAM platform"
```

Create a new repo on GitHub (e.g. `stream-catalog`), then:

```bash
git remote add origin git@github.com:YOUR_USER/stream-catalog.git
git branch -M main
git push -u origin main
```

---

## 2. Create a cloud database (PostgreSQL)

SQLite is local-only. Use a free **Neon** Postgres (or RDS):

1. Go to [neon.tech](https://neon.tech) → create project → copy the connection string.
2. It looks like:
   `postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require`

You will use this as `DATABASE_URL` on App Runner.

---

## 3. Deploy the API on AWS App Runner

App Runner builds the `backend/Dockerfile` from your GitHub repo.

1. AWS Console → **App Runner** → **Create service**.
2. **Source**: Repository → connect **GitHub** → select `stream-catalog`.
3. **Root directory**: `backend`
4. **Build**: Dockerfile (automatic).
5. **Port**: `8000`
6. **Environment variables**:

   | Name | Value |
   |------|--------|
   | `DATABASE_URL` | Your Neon Postgres URL |
   | `CORS_ORIGINS` | `https://main.dXXXXXXXX.amplifyapp.com` (fill in after Amplify step 4, or use `*` temporarily) |
   | `SEED_ON_STARTUP` | `true` (first deploy only; set `false` later) |

7. Deploy. Copy the **default domain**, e.g. `https://abc123.us-east-1.awsapprunner.com`.
8. Verify: open `https://YOUR-APP-RUNNER-URL/health` → `{"status":"ok"}`.

---

## 4. Deploy the frontend on AWS Amplify

1. AWS Console → **Amplify** → **Create new app** → **Host web app**.
2. Connect **GitHub** → select `stream-catalog` → branch `main`.
3. Amplify detects `amplify.yml` and sets **app root** to `frontend`.
4. **Environment variables** (Amplify → App settings → Environment variables):

   | Name | Value |
   |------|--------|
   | `VITE_API_URL` | `https://YOUR-APP-RUNNER-URL` (no trailing slash) |

5. Save and deploy.
6. Copy your Amplify URL, e.g. `https://main.d1234abcdef.amplifyapp.com`.

---

## 5. Wire CORS (required once)

Go back to **App Runner** → your service → **Configuration** → **Environment variables**:

- Set `CORS_ORIGINS` to your Amplify URL (comma-separated if you add custom domains):
  ```
  https://main.d1234abcdef.amplifyapp.com,https://catalog.yourdomain.com
  ```
- Redeploy if App Runner does not auto-restart.

---

## 6. Use from any computer

| What | URL |
|------|-----|
| Admin UI | Amplify URL |
| API docs | `https://YOUR-APP-RUNNER-URL/docs` |
| Code | `github.com/YOUR_USER/stream-catalog` |

**Workflow on a new machine:**

```bash
git clone git@github.com:YOUR_USER/stream-catalog.git
cd stream-catalog
# optional local dev:
cd backend && python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && uvicorn app.main:app --reload
```

Cloud UI/API already use the shared Postgres DB — no need to copy `catalog.db`.

---

## 7. Custom domain (optional)

**Amplify**: Domain management → add domain → follow DNS steps.

**App Runner**: Custom domains → add subdomain (e.g. `api.catalog.example.com`).

Update `CORS_ORIGINS` and `VITE_API_URL` accordingly, then redeploy both.

---

## 8. Ongoing deploys

| Change | What redeploys |
|--------|----------------|
| Push to `main` (frontend files) | Amplify auto-builds |
| Push to `main` (backend files) | App Runner auto-rebuilds (if auto-deploy enabled) |
| Env var change | Redeploy in Amplify / App Runner console |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| UI loads but API errors | Check `VITE_API_URL` in Amplify matches App Runner URL |
| CORS error in browser | Add exact Amplify URL to `CORS_ORIGINS` on App Runner |
| Empty catalog in cloud | Set `SEED_ON_STARTUP=true`, redeploy once, then `false` |
| 404 on `/titles` refresh | `_redirects` in `frontend/public/` handles SPA routes |
| Build fails on Amplify | Ensure `appRoot: frontend` in `amplify.yml` |

---

## Cost note

- **Amplify Hosting**: free tier for low traffic.
- **App Runner**: ~$5+/mo when always on.
- **Neon Postgres**: free tier available.

For minimal cost, use Amplify + App Runner + Neon free tiers while building.
