# PrivacyShield OSS — Complete Setup Instructions

> **100% open-source.** No Google API keys, no Stripe, no SendGrid, no AWS account required.

---

## What's Inside

```
privacyshield-oss/
├── backend/               FastAPI + Python 3.11
│   ├── app/
│   │   ├── api/v1/        REST endpoints (auth, scans, removals, extension)
│   │   ├── core/          JWT security, exceptions
│   │   ├── models/        SQLAlchemy ORM (User, Scan, RemovalRequest, APIKey)
│   │   ├── services/
│   │   │   ├── nlp/       4-layer PII detector (Presidio → spaCy → BERT → co-occurrence)
│   │   │   ├── crawler/   SearXNG search + async page fetcher (SSRF-safe)
│   │   │   ├── removal/   Data broker opt-out automation (Playwright)
│   │   │   ├── email/     SMTP via aiosmtplib (Mailhog dev / Postfix prod)
│   │   │   ├── secrets/   HashiCorp Vault loader
│   │   │   └── storage/   MinIO client
│   │   └── workers/       Celery tasks + beat scheduler
│   ├── alembic/           DB migrations
│   ├── tests/             pytest suite (auth + NLP unit tests)
│   └── data/              data_brokers.json (15 brokers)
├── frontend/              React 18 + TypeScript + Tailwind CSS
│   └── src/
│       ├── pages/         Dashboard, Login, NewScan, ScanDetail
│       ├── components/    Layout, sidebar
│       ├── api/           Axios client + interceptors
│       └── store/         JWT auth context
├── extension/             Chrome Manifest V3 browser extension
├── infra/
│   ├── k8s/               5 Kubernetes manifests (namespace, secrets, backend, worker, ingress)
│   ├── searxng/           SearXNG config
│   └── prometheus/        Prometheus scrape config
├── docs/
│   ├── APPSEC_REVIEW.md   Full OWASP Top 10 security audit
│   └── DEPLOYMENT_RUNBOOK.md
├── docker-compose.yml     Complete OSS stack
└── INSTRUCTIONS.md        This file
```

---

## OSS Service Map

| Proprietary | OSS Replacement | License | Port |
|-------------|-----------------|---------|------|
| Google Custom Search API | **SearXNG** (self-hosted) | AGPL-3.0 | 8888 |
| SendGrid | **Mailhog** (dev) / Stalwart (prod) | MIT / Apache-2.0 | 1025/8025 |
| AWS S3 | **MinIO** | Apache-2.0 | 9000/9001 |
| AWS Secrets Manager | **HashiCorp Vault OSS ≤1.13** / OpenBao | MPL-2.0 | 8200 |
| Sentry SaaS | **GlitchTip** | MIT | 8010 |
| Stripe | **Kill-Bill** | Apache-2.0 | 8080/9090 |
| AWS EKS | Generic K8s / **K3s** | Apache-2.0 | — |
| Sentry SDK | Same SDK, points to GlitchTip | MIT | — |

---

## Prerequisites

```bash
# Required
docker --version        # >= 25.0
docker compose version  # >= 2.24
git --version

# For local development without Docker
python --version        # 3.11+
node --version          # 20+
```

---

## Quick Start (5 minutes)

### Step 1 — Clone / extract

```bash
# If from zip:
unzip privacyshield-oss.zip
cd privacyshield-oss

# If from git:
git clone https://github.com/your-org/privacyshield-oss.git
cd privacyshield-oss
```

### Step 2 — Configure environment

```bash
cp backend/.env.example backend/.env

# Edit one value — the rest are pre-configured for local dev:
# Set SECRET_KEY to a random 64-char string:
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
# Paste that line into backend/.env
```

### Step 3 — Start all services

```bash
docker compose up --build
```

First run takes **5–10 minutes** (downloads images, builds containers, downloads spaCy model).
Subsequent starts take ~30 seconds.

### Step 4 — Run DB migrations

```bash
# In a new terminal (while services are running):
docker compose exec backend alembic upgrade head
```

### Step 5 — Access the stack

| Service | URL | Credentials |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | register new account |
| **API docs** | http://localhost:8000/docs | — |
| **Mailhog** (email) | http://localhost:8025 | — (catches all emails) |
| **MinIO** (storage) | http://localhost:9001 | minioadmin / minioadmin |
| **Vault** | http://localhost:8200 | Token: `dev-root-token` |
| **GlitchTip** (errors) | http://localhost:8010 | create account |
| **Flower** (queue) | http://localhost:5555 | — |
| **Kill-Bill** (billing) | http://localhost:9090 | admin / password |
| **Grafana** | http://localhost:3001 | admin / admin |
| **Prometheus** | http://localhost:9091 | — |
| **SearXNG** | http://localhost:8888 | — |

---

## Run Tests

```bash
# All tests
docker compose exec backend pytest tests/ -v --cov=app --cov-report=term-missing

# Auth tests only
docker compose exec backend pytest tests/test_auth.py -v

# NLP unit tests (fast, no ML models needed)
docker compose exec backend pytest tests/test_nlp.py -v
```

---

## Run Security Scans

```bash
# SAST — Bandit
docker compose exec backend bandit -r app/ -ll --skip B101,B601

# Dependency CVEs — Safety
docker compose exec backend safety check -r requirements.txt

# Dependency audit — pip-audit
docker compose exec backend pip-audit -r requirements.txt
```

---

## Load spaCy NLP Models

The full AI pipeline requires transformer models (~500 MB each):

```bash
# Inside backend container:
docker compose exec backend python -m spacy download en_core_web_trf

# Lighter alternative (faster, lower accuracy):
docker compose exec backend python -m spacy download en_core_web_sm
```

Models are cached in the container. For production, bake them into the Docker image:
```dockerfile
# Add to backend/Dockerfile builder stage:
RUN /build/venv/bin/python -m spacy download en_core_web_trf
```

---

## Vault Setup (Secrets Management)

In dev mode, Vault runs unseal and accepts all requests with token `dev-root-token`.

To store production secrets in Vault:

```bash
# Set your secrets (run once)
docker compose exec vault vault kv put secret/privacyshield/production \
  SECRET_KEY="your-64-char-secret" \
  DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db" \
  SMTP_HOST="your-smtp-host" \
  MINIO_SECRET_KEY="your-minio-key"

# Verify
docker compose exec vault vault kv get secret/privacyshield/production
```

The backend automatically loads Vault secrets at startup via `vault_loader.py`.

---

## GlitchTip Setup (Error Monitoring)

1. Go to http://localhost:8010
2. Register an account
3. Create an organization → project → **Django** type
4. Copy the **DSN** (looks like `http://abc123@localhost:8010/1`)
5. Add to `backend/.env`:
   ```
   SENTRY_DSN=http://abc123@localhost:8010/1
   ```
6. Restart backend: `docker compose restart backend`

---

## SearXNG Configuration

SearXNG is pre-configured at `infra/searxng/settings.yml`.

To add/remove search engines, edit the `engines:` section:
```yaml
engines:
  - name: google
    engine: google
    shortcut: g
  - name: bing
    engine: bing
    shortcut: b
```

> **Note:** Some search engines block automated queries over time. Add more engines (Brave, Startpage, Qwant) to improve resilience.

---

## Browser Extension

### Load in Chrome/Edge
1. Open `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `extension/src/` directory

### Load in Firefox
1. Open `about:debugging`
2. Click **This Firefox** → **Load Temporary Add-on**
3. Select `extension/src/manifest.json`

The extension alerts you when visiting data broker sites (Spokeo, Whitepages, etc.) with PII matches.

---

## Production Deployment (K3s / Kubernetes)

K3s is a lightweight certified Kubernetes distribution (Apache-2.0):

```bash
# Install K3s on a Linux server (1 command)
curl -sfL https://get.k3s.io | sh -

# Copy kubeconfig
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Deploy PrivacyShield
kubectl apply -f infra/k8s/

# Check pods
kubectl get pods -n privacyshield
```

For production, replace `hashicorp/vault:1.13.13` with **OpenBao** (the fully-OSS MPL-2.0 Vault fork):
```yaml
image: openbao/openbao:2.0.0   # MPL-2.0 fork of Vault
```

---

## Stop / Clean Up

```bash
# Stop all containers
docker compose down

# Stop and wipe all data volumes
docker compose down -v

# Remove built images
docker compose down --rmi all
```

---

## Architecture Summary

```
Browser → Frontend (React)
            ↓ HTTPS
          Backend (FastAPI) ──→ PostgreSQL 16
            ↓                 ↘ Redis 7
          Celery Worker         ↓
            ↓            Task queue (Redis)
          AI Pipeline
           ├─ Presidio (regex PII)
           ├─ spaCy transformer NER
           ├─ BERT NER (dslim/bert-base-NER)
           └─ Co-occurrence scorer
            ↓
          SearXNG ────→ Google/Bing/DDG (via SearXNG proxy)
          PageFetcher → Data broker sites (SSRF-safe)
          Playwright  → Automated form opt-outs
            ↓
          MinIO (reports)
          Mailhog/SMTP (notifications)
          Vault (secrets)
          GlitchTip (errors)
          Prometheus + Grafana (metrics)
```

---

## Troubleshooting

**Port already in use:**
```bash
# Change conflicting port in docker-compose.yml e.g. "8888:8080" → "8889:8080"
```

**Backend won't start — missing env vars:**
```bash
docker compose logs backend | tail -30
# Ensure backend/.env exists and SECRET_KEY is set
```

**SearXNG returns no results:**
```bash
# Some engines block scrapers; test manually:
curl "http://localhost:8888/search?q=test&format=json"
# If empty, edit infra/searxng/settings.yml and add more engines
```

**spaCy model not found:**
```bash
docker compose exec backend python -m spacy download en_core_web_sm
```

**Vault sealed in production:**
```bash
docker compose exec vault vault operator unseal
# Enter the unseal key (generated on first `vault operator init`)
```

---

## License Summary

All components are open-source. No proprietary dependencies.

| Component | License |
|-----------|---------|
| FastAPI, Pydantic, SQLAlchemy | MIT |
| spaCy, Transformers, Presidio | MIT / Apache-2.0 |
| PostgreSQL, Redis | PostgreSQL License / BSD |
| SearXNG | AGPL-3.0 |
| Celery, Flower | BSD |
| MinIO | Apache-2.0 |
| HashiCorp Vault ≤1.13 / OpenBao | MPL-2.0 |
| GlitchTip | MIT |
| Kill-Bill | Apache-2.0 |
| Prometheus, Grafana | Apache-2.0 / AGPL-3.0 |
| Mailhog | MIT |
| React, Tailwind, Vite | MIT |
| Playwright | Apache-2.0 |
