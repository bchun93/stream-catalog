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
    └── Render      →  https://stream-catalog.onrender.com (your dashboard URL)
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
4. When prompted, set secrets (**required**):
   - `DATABASE_URL` — Neon PostgreSQL URL (must include `?sslmode=require` if not already). **Without this, metadata import works but Titles/list/create fail.**
   - `TMDB_API_KEY` — [TMDB v3 key](https://www.themoviedb.org/settings/api)
5. Deploy. Copy the service URL from the Render dashboard (e.g. `https://stream-catalog.onrender.com`).
6. Verify:

```bash
./scripts/verify-cloud.sh https://stream-catalog.onrender.com
```

Expect `{"ok":true}` for metadata health.

7. After first deploy, set `SEED_ON_STARTUP` to `false` in Render → Environment.

**Free tier note:** Render free web services spin down after inactivity; first request may take ~30s.

### Manual deploy (without Blueprint)

**New +** → **Web Service** → **Docker** → settings:

| Setting | Value |
|---------|--------|
| Root Directory | *(leave empty — uses repo root `Dockerfile`)* |
| Dockerfile path | `Dockerfile` |
| Health Check Path | `/health` |

Or set **Root Directory** to `backend` and Dockerfile to `Dockerfile` there.

Add env vars: `DATABASE_URL`, `TMDB_API_KEY`, `SEED_ON_STARTUP`.

For **Upload / S3** on Render, also set:

| Name | Notes |
|------|--------|
| `INGEST_S3_BUCKET` | e.g. `stream-catalog-ingest` |
| `AWS_ACCESS_KEY_ID` | IAM user with S3 put/get on the ingest bucket |
| `AWS_SECRET_ACCESS_KEY` | Matching secret |
| `S3_MUTATION_SECRET` | Random 32+ character server-only secret used to authenticate resumable rename state |
| `AWS_REGION` | Bucket region (e.g. `ap-northeast-1`) |
| `INGEST_OPERATOR_TOKEN` | Required in production when Upload/S3 is enabled; protects presign routes |
| `ADMIN_API_KEY` | Protects mutating title/admin routes |

Without `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or a working default AWS credential chain / instance role), Upload fails with a credentials error (botocore `Unable to locate credentials`, or Relay’s clearer “AWS credentials are not configured for S3” message).

The IAM identity needs `s3:ListBucket` on the bucket and `s3:GetObject`,
`s3:PutObject`, `s3:DeleteObject`, and `s3:AbortMultipartUpload` on the
configured ingest prefix. Rename uses conditional multipart copy-then-delete,
supports large objects, and never overwrites an existing key.
Generate `S3_MUTATION_SECRET` with `openssl rand -hex 32`; changing it while a
rename is partially complete prevents automatic reconciliation of that rename.

Do **not** set `PORT` manually — Render injects it (often `10000`). The container must listen on `$PORT`.

If logs show `HEAD / HTTP/1.1" 404`, the health check path is wrong or the deploy is on an old build without the `/` route fix.

### Build error: `open Dockerfile: no such file or directory`

Render was building from the repo root but looking for `Dockerfile` there. The repo now includes a **root `Dockerfile`**. Redeploy from the latest `main` commit (includes `render.yaml`).

---

## 4. Deploy the frontend on Amplify

1. AWS Amplify → **Host web app** → connect GitHub → `stream-catalog` → branch `main`.
2. `amplify.yml` sets `appRoot: frontend`.
3. **Environment variables** (required):

| Name | Value |
|------|--------|
| `VITE_API_URL` | `https://stream-catalog.onrender.com` (your Render URL, no trailing slash) |

Do **not** add `INGEST_OPERATOR_TOKEN` or `ADMIN_API_KEY` as `VITE_*` Amplify
variables: Vite embeds those values in public JavaScript. The UI prompts for
the corresponding Render token at runtime and keeps it only in the current
browser tab.

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
| Titles show **Failed to fetch** but API sidebar says Connected | Redeploy Amplify (GET must not send `Content-Type` — fixed in client). Run `./scripts/verify-cloud.sh` |
| API status shows error | Check Render logs; verify `/health` |
| Slow first search | Render free tier cold start — wait or upgrade plan |
| CORS error / "Failed to fetch" on Amplify | Redeploy **Render** after CORS fix; Amplify URLs look like `main.xxxx.amplifyapp.com` |
| Build fails on Amplify | Set `VITE_API_URL` in Amplify env vars |
| Render: `Application startup failed` + SQLAlchemy link | Wrong `DATABASE_URL`, or reset Neon DB (see below) |

### Render startup failed (SQLAlchemy / seed)

Usually one of:

1. **`DATABASE_URL` is wrong** — must be full Neon URL starting with `postgresql://`, not `neon`.
2. **PostgreSQL enum conflict** — partial failed deploy left bad schema. In Neon → **SQL Editor** run:
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   ```
   Then redeploy Render.
3. Set `SEED_ON_STARTUP=false` in Render if you don't need sample data on every boot.

---

## Cost (typical)

- **Amplify** — free tier for low traffic
- **Render** — free web service available; paid from ~$7/mo always-on
- **Neon** — free tier available
