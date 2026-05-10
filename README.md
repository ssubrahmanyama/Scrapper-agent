# PrivacyShield AI

> **AI-powered personal data privacy protection for the Indian & global market**
> DPDP Act 2023 compliant · GDPR-ready · CCPA support

---

## What It Does

PrivacyShield automatically scans the internet for your personal data (PII) on data broker sites, people-search engines, and public databases — then files automated removal requests on your behalf.

| Feature | Description |
|---------|-------------|
| 🔍 AI PII Scan | Multi-layer detection (Presidio + spaCy transformer + BERT NER) |
| 🤖 Auto-Removal | Automated opt-out submissions to 500+ data broker sites |
| 🛡️ Browser Extension | Real-time alerts when visiting data broker sites |
| 📊 Exposure Score | 0–100 risk score with co-occurrence analysis |
| 🔄 Weekly Re-scans | Automated monitoring via Celery Beat |
| 🏢 Enterprise API | API key auth for B2B integrations |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    privacyshield.ai                      │
│  React SPA (Vite + TypeScript + Tailwind)                │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────┐
│              FastAPI Backend (Python 3.11)               │
│  Auth · Scans · Removals · Enterprise API · Extension    │
└──────┬────────────────────────────┬─────────────────────┘
       │                            │
┌──────▼──────┐            ┌────────▼────────┐
│  PostgreSQL  │            │  Celery Workers │
│  (RDS 16)   │            │  (Scan + Remove)│
└─────────────┘            └────────┬────────┘
                                    │
┌───────────────────────────────────▼────────────────────┐
│                    AI Pipeline                          │
│  Layer 1: Presidio (regex)                             │
│  Layer 2: spaCy en_core_web_trf (transformer NER)      │
│  Layer 3: BERT NER (dslim/bert-base-NER)               │
│  Layer 4: Co-occurrence analysis                        │
└────────────────────────────────────────────────────────┘
```

---

## Quick Start (Local Dev)

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 20+

### 1. Clone and configure
```bash
git clone https://github.com/your-org/privacyshield.git
cd privacyshield
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
```

### 2. Start everything
```bash
docker compose up --build
```

### 3. Access services
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Celery Flower | http://localhost:5555 |

### 4. Run DB migrations
```bash
docker compose exec backend alembic upgrade head
```

### 5. Run tests
```bash
docker compose exec backend pytest tests/ -v --cov=app
```

---

## Project Structure

```
privacyshield/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI routers
│   │   ├── core/            # Security, exceptions
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/
│   │   │   ├── crawler/     # Google Search + PageFetcher
│   │   │   ├── nlp/         # PII detector + scorer
│   │   │   └── removal/     # Data broker removal engine
│   │   └── workers/         # Celery tasks
│   ├── alembic/             # DB migrations
│   ├── tests/               # pytest test suite
│   └── data/                # data_brokers.json
├── frontend/
│   └── src/
│       ├── api/             # Axios client
│       ├── pages/           # React page components
│       ├── components/      # UI components
│       └── store/           # Auth context
├── extension/
│   └── src/                 # Chrome Manifest V3 extension
├── infra/
│   ├── k8s/                 # Kubernetes manifests
│   └── terraform/           # AWS infrastructure (TBD)
└── docs/
    ├── APPSEC_REVIEW.md     # Full security audit
    └── DEPLOYMENT_RUNBOOK.md
```

---

## Security Highlights

- **Zero hardcoded secrets** — all via AWS Secrets Manager
- **JWT with refresh token rotation** — theft detection built-in
- **SSRF protection** — private IP ranges blocked in crawler
- **PII masking** — raw PII never stored or logged
- **Non-root containers** — UID 1000, all capabilities dropped
- **NetworkPolicy** — default-deny Kubernetes network isolation
- **Trivy + Bandit + Safety** — automated CVE scanning in CI/CD

See [`docs/APPSEC_REVIEW.md`](docs/APPSEC_REVIEW.md) for the full security audit.

---

## Deployment

See [`docs/DEPLOYMENT_RUNBOOK.md`](docs/DEPLOYMENT_RUNBOOK.md) for the complete production deployment guide.

**Quick deploy to EKS:**
```bash
kubectl apply -f infra/k8s/
```

CI/CD is fully automated via GitHub Actions — see [`.github/workflows/ci-cd.yaml`](.github/workflows/ci-cd.yaml).

---

## API Documentation

Production API docs are disabled. In development:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Key Endpoints
```
POST /api/v1/auth/register   — Register
POST /api/v1/auth/login      — Login (returns JWT)
POST /api/v1/auth/refresh    — Refresh token
POST /api/v1/scans           — Start a new scan
GET  /api/v1/scans/{id}      — Get scan results
GET  /api/v1/removals        — List removal requests
POST /api/v1/extension/analyse — Browser extension PII check
```

---

## Subscription Tiers

| Feature | Free | Basic | Pro | Enterprise |
|---------|------|-------|-----|------------|
| Scans/day | 1 | 5 | 50 | 1000 |
| Auto-removal | ✗ | ✓ | ✓ | ✓ |
| Weekly re-scan | ✗ | ✗ | ✓ | ✓ |
| API access | ✗ | ✗ | ✗ | ✓ |
| SLA | — | — | 99.9% | 99.99% |

---

## Compliance

| Standard | Status |
|----------|--------|
| DPDP Act 2023 (India) | ✅ Data minimisation, right to erasure, localisation |
| GDPR Article 17 | ✅ Right to erasure supported |
| CCPA | ✅ Opt-out automation |
| ISO 27001 controls | ✅ Applied (not certified) |

---

## License

Proprietary — PrivacyShield Technologies Pvt. Ltd. © 2025
