# Deploy Stream Catalog (Amplify + Render)

AWS **App Runner** is in [maintenance mode](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html) (no new customers). This project uses:

| Layer | Service | Role |
|-------|---------|------|
| **UI** | **AWS Amplify** | React admin (static hosting) |
| **API** | **[Render](https://render.com)** | FastAPI via `backend/Dockerfile` |
| **DB** | **Neon Postgres** | Shared cloud database |

```
GitHub repo
    ├── Amplify     →  https://main.xxxxx.amplifyapp.com
    └── Render      →  https://stream-catalog-api.onrender.com
              │
              └── Neon PostgreSQL
```

---

## 1. Push code to GitHub

```bash
cd stream-catalog
git push origin main
```

---

## 2. Create PostgreSQL (Neon)

1. [neon.tech](https://neon.tech) → new project → copy connection string.
2. Format: `postgresql://user:pass@host.neon.tech/db?sslmode=require`

---

## 3. Deploy the API on Render (recommended)

Uses `render.yaml` in the repo root.

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**.
2. Connect **GitHub** → select `stream-catalog`.
3. Render reads `render.yaml` and creates **stream-catalog-api**.
4. When prompted, set secrets:
   - `DATABASE_URL` — Neon URL
   - `TMDB_API_KEY` — [TMDB v3 key](https://www.themoviedb.org/settings/api)
5. Deploy. Copy the service URL, e.g. `https://stream-catalog-api.onrender.com`.
6. Verify:

```bash
./scripts/verify-cloud.sh https://stream-catalog-api.onrender.com
```

Expect `{"ok":true}` for metadata health.

7. After first deploy, set `SEED_ON_STARTUP` to `false` in Render → Environment.

**Free tier note:** Render free web services spin down after inactivity; first request may take ~30s.

### Manual deploy (without Blueprint)

**New +** → **Web Service** → Docker → root directory `backend` → add the same env vars.

---

## 4. Deploy the frontend on Amplify

1. AWS Amplify → **Host web app** → connect GitHub → `stream-catalog` → branch `main`.
2. `amplify.yml` sets `appRoot: frontend`.
3. **Environment variables** (required):

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://stream-catalog-api.onrender.com` (your Render URL, no trailing slash) |

4. Deploy. Build **fails** if `VITE_API_URL` is missing (by design).

---

## 5. Wire Amplify to Render (script)

```bash
cp deploy.env.example deploy.env
# Set AMPLIFY_APP_ID, API_URL (Render), DATABASE_URL, TMDB_API_KEY

chmod +x scripts/deploy-cloud.sh scripts/verify-cloud.sh
./scripts/deploy-cloud.sh
```

---

## 6. CORS

The API automatically allows:

- `*.amplifyapp.com`
- `*.onrender.com`

Optional `CORS_ORIGINS` for custom domains.

---

## 7. Verify in the browser

Open your Amplify URL. Sidebar should show **API · Connected · TMDB ok**.

**Titles → + New title →** search `gladiator`.

---

## AWS-native alternative (ECS Express Mode)

If you must stay on AWS, AWS recommends **[ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-mode.html)** instead of App Runner:

- Provisions Fargate + load balancer from a container image
- Use the same `backend/Dockerfile`
- Set the same env vars (`DATABASE_URL`, `TMDB_API_KEY`, etc.)
- Put the ALB URL in Amplify `VITE_API_URL`

Other options: standard **ECS Fargate**, **Lambda + API Gateway** (requires [Mangum](https://mangum.io/) adapter), **Lightsail containers**.

---

## Ongoing deploys

| Change | Redeploys |
|--------|-----------|
| Frontend push to `main` | Amplify |
| Backend push to `main` | Render |
| `VITE_API_URL` change | Amplify rebuild required |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Metadata works locally, not on Amplify | Set `VITE_API_URL` to Render URL; redeploy Amplify |
| API status shows error | Check Render logs; verify `/health` |
| Slow first search | Render free tier cold start — wait or upgrade plan |
| CORS error | Confirm Amplify URL matches `*.amplifyapp.com` pattern |
| Build fails on Amplify | Set `VITE_API_URL` in Amplify env vars |

---

## Cost (typical)

- **Amplify** — free tier for low traffic
- **Render** — free web service available; paid from ~$7/mo always-on
- **Neon** — free tier available
