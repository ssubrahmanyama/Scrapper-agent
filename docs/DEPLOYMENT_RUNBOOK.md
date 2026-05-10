# PrivacyShield — Production Deployment Runbook
**Version:** 1.0 | **Environment:** AWS EKS (ap-south-1)
**Audience:** DevOps / Platform Engineer

---

## Architecture Overview

```
Internet → CloudFront CDN → ALB (nginx-ingress)
                                 ├── privacyshield.ai     → Frontend (nginx pods)
                                 └── api.privacyshield.ai → Backend (FastAPI pods)
                                                                 ├── RDS PostgreSQL 16
                                                                 ├── ElastiCache Redis 7
                                                                 └── Celery Workers
                                                                          ├── Scan tasks
                                                                          ├── Removal tasks
                                                                          └── Beat scheduler
```

---

## Prerequisites

### Tools Required
```bash
# Check versions
aws --version          # >= 2.15
kubectl version        # >= 1.29
helm version           # >= 3.14
terraform version      # >= 1.7
docker version         # >= 25
```

### AWS Resources (pre-provisioned via Terraform)
- EKS Cluster: `privacyshield-prod` (Kubernetes 1.29)
- RDS: PostgreSQL 16 Multi-AZ (db.r6g.large)
- ElastiCache: Redis 7 cluster (cache.r6g.large, 2 nodes)
- S3 bucket: `privacyshield-exports`
- ECR / GHCR: Container registry
- KMS key: `privacyshield/production`
- ACM certificate: `*.privacyshield.ai`

---

## Phase 1 — First-Time Cluster Setup

### 1.1 Configure kubectl
```bash
aws configure --profile privacyshield
# Enter: AWS Access Key, Secret Key, Region: ap-south-1, Output: json

aws eks update-kubeconfig \
  --name privacyshield-prod \
  --region ap-south-1 \
  --profile privacyshield
```

### 1.2 Install cluster add-ons
```bash
# cert-manager (TLS certificates)
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true \
  --version v1.14.5

# nginx-ingress controller
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.service.type=LoadBalancer \
  --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb

# External Secrets Operator (for AWS Secrets Manager)
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace

# Prometheus + Grafana stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### 1.3 Configure Let's Encrypt ClusterIssuer
```bash
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: devops@privacyshield.ai
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
EOF
```

### 1.4 Configure External Secrets ClusterSecretStore
```bash
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secretsmanager
spec:
  provider:
    aws:
      service: SecretsManager
      region: ap-south-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
            namespace: external-secrets
EOF
```

---

## Phase 2 — Secrets Provisioning

### 2.1 Create secrets in AWS Secrets Manager
```bash
aws secretsmanager create-secret \
  --name privacyshield/production \
  --region ap-south-1 \
  --secret-string '{
    "SECRET_KEY": "'$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")'",
    "DATABASE_URL": "postgresql+asyncpg://privacyshield:<PASSWORD>@<RDS_ENDPOINT>:5432/privacyshield",
    "REDIS_URL": "redis://<ELASTICACHE_ENDPOINT>:6379/0",
    "CELERY_BROKER_URL": "redis://<ELASTICACHE_ENDPOINT>:6379/1",
    "CELERY_RESULT_BACKEND": "redis://<ELASTICACHE_ENDPOINT>:6379/2",
    "GOOGLE_CUSTOM_SEARCH_API_KEY": "<YOUR_KEY>",
    "GOOGLE_SEARCH_ENGINE_ID": "<YOUR_CX_ID>",
    "SENDGRID_API_KEY": "<YOUR_KEY>",
    "STRIPE_SECRET_KEY": "<YOUR_KEY>",
    "STRIPE_WEBHOOK_SECRET": "<YOUR_KEY>",
    "STRIPE_PRICE_BASIC": "price_xxx",
    "STRIPE_PRICE_PRO": "price_yyy",
    "STRIPE_PRICE_ENTERPRISE": "price_zzz",
    "SENTRY_DSN": "<YOUR_DSN>",
    "AWS_ACCESS_KEY_ID": "<FOR_S3>",
    "AWS_SECRET_ACCESS_KEY": "<FOR_S3>",
    "BACKEND_CORS_ORIGINS": "https://privacyshield.ai,https://www.privacyshield.ai"
  }'
```

### 2.2 Verify secrets sync
```bash
kubectl get externalsecret -n privacyshield
# Expected: privacyshield-secrets   SecretSynced   True   ...
kubectl get secret privacyshield-secrets -n privacyshield -o jsonpath='{.data}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d.keys()))"
```

---

## Phase 3 — Database Setup

### 3.1 Run initial migrations
```bash
# Port-forward to run Alembic locally (first deploy only)
kubectl run alembic-migrate --rm -it \
  --image=ghcr.io/your-org/privacyshield-backend:latest \
  --env-from=secret/privacyshield-secrets \
  --env-from=configmap/privacyshield-config \
  --restart=Never \
  -n privacyshield \
  -- alembic upgrade head

# Verify
kubectl run psql-check --rm -it \
  --image=postgres:16-alpine \
  --restart=Never \
  -n privacyshield \
  --env="PGPASSWORD=<PASSWORD>" \
  -- psql -h <RDS_ENDPOINT> -U privacyshield -d privacyshield -c "\dt"
```

---

## Phase 4 — Application Deployment

### 4.1 Apply all manifests (first deploy)
```bash
# Apply in order
kubectl apply -f infra/k8s/00-namespace.yaml
sleep 5
kubectl apply -f infra/k8s/01-config-secrets.yaml
# Wait for ExternalSecret to sync
kubectl wait --for=condition=Ready externalsecret/privacyshield-secrets -n privacyshield --timeout=120s
kubectl apply -f infra/k8s/02-backend.yaml
kubectl apply -f infra/k8s/03-worker.yaml
kubectl apply -f infra/k8s/04-frontend-ingress.yaml
```

### 4.2 Verify deployments
```bash
# All pods should be Running
kubectl get pods -n privacyshield -w

# Backend health
kubectl exec -n privacyshield deploy/backend -- curl -s localhost:8000/health
kubectl exec -n privacyshield deploy/backend -- curl -s localhost:8000/ready

# Check logs
kubectl logs -n privacyshield -l app=backend --tail=50
kubectl logs -n privacyshield -l app=worker --tail=50
```

### 4.3 Verify ingress
```bash
kubectl get ingress -n privacyshield
# Note the ADDRESS field — point DNS to it

# Test TLS
curl -I https://api.privacyshield.ai/health
# Expect: HTTP/2 200, Strict-Transport-Security header present
```

---

## Phase 5 — DNS Configuration

```
# In your DNS provider (Cloudflare recommended):

Type: CNAME  Name: @           Value: <ALB_DNS_NAME>
Type: CNAME  Name: www         Value: <ALB_DNS_NAME>
Type: CNAME  Name: api         Value: <ALB_DNS_NAME>

# For Cloudflare: set proxy mode to "DNS only" initially,
# then enable proxy after TLS certificate is provisioned.
```

---

## Phase 6 — Post-Deploy Verification

### 6.1 Smoke tests
```bash
# Health endpoints
curl https://api.privacyshield.ai/health
curl https://privacyshield.ai/health

# Register + login flow
curl -X POST https://api.privacyshield.ai/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"smoketest@example.com","password":"SmokeTest123!","full_name":"Smoke Test"}'

# SSL grade check
# Navigate to: https://www.ssllabs.com/ssltest/analyze.html?d=api.privacyshield.ai
# Expect: A+ grade

# Security headers check
# Navigate to: https://securityheaders.com/?q=api.privacyshield.ai
# Expect: A grade
```

### 6.2 Verify monitoring
```bash
# Port-forward Grafana
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# Access: http://localhost:3000 (admin/prom-operator)
# Import dashboards: FastAPI, Celery, PostgreSQL, Redis
```

---

## Rolling Update Procedure (Routine Deploys)

```bash
# Triggered automatically by CI/CD on merge to main
# Manual override:

NEW_TAG="sha-<git_sha>"

kubectl set image deployment/backend \
  backend=ghcr.io/your-org/privacyshield-backend:${NEW_TAG} \
  -n privacyshield

kubectl rollout status deployment/backend -n privacyshield --timeout=300s

# Verify
kubectl get pods -n privacyshield -l app=backend
kubectl logs -n privacyshield -l app=backend --tail=20
```

---

## Rollback Procedure

```bash
# Instant rollback to previous revision
kubectl rollout undo deployment/backend -n privacyshield
kubectl rollout undo deployment/worker -n privacyshield
kubectl rollout undo deployment/frontend -n privacyshield

# Verify
kubectl rollout status deployment/backend -n privacyshield
kubectl get pods -n privacyshield

# Check history
kubectl rollout history deployment/backend -n privacyshield
```

---

## Database Backup & Recovery

```bash
# Manual snapshot (automated daily via AWS RDS automated backups)
aws rds create-db-snapshot \
  --db-instance-identifier privacyshield-prod \
  --db-snapshot-identifier privacyshield-manual-$(date +%Y%m%d-%H%M)

# Restore to point-in-time
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier privacyshield-prod \
  --target-db-instance-identifier privacyshield-restore \
  --restore-time "2025-01-15T06:00:00Z"
```

---

## Scaling Operations

```bash
# Manual scale (e.g., pre-spike)
kubectl scale deployment/backend --replicas=10 -n privacyshield
kubectl scale deployment/worker  --replicas=6  -n privacyshield

# View current HPA status
kubectl get hpa -n privacyshield

# Describe HPA events
kubectl describe hpa backend-hpa -n privacyshield
```

---

## Incident Response

### API is down
```bash
1. kubectl get pods -n privacyshield         # Check pod status
2. kubectl describe pod <pod_name> -n privacyshield   # Check events
3. kubectl logs <pod_name> -n privacyshield --previous  # Crash logs
4. kubectl rollout undo deployment/backend -n privacyshield  # Rollback if recent deploy
5. Check Sentry for error spike
6. Check RDS / Redis connectivity via readiness probe
```

### High error rate
```bash
1. Check Grafana dashboard for error rate spike
2. kubectl logs -n privacyshield -l app=backend --tail=100 | grep ERROR
3. Check Sentry for stack traces
4. Scale up if CPU/memory bounded: kubectl scale deployment/backend --replicas=+2
```

### Database connection exhausted
```bash
1. Check pool: kubectl exec deploy/backend -- python -c "from app.database import engine; print(engine.pool.status())"
2. Reduce pool size temporarily via env var patch
3. Identify long-running queries: SELECT pid, query, state, now() - query_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;
```

---

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | JWT signing key (64+ chars) | ✅ |
| `DATABASE_URL` | PostgreSQL async DSN | ✅ |
| `REDIS_URL` | Redis DSN for caching | ✅ |
| `CELERY_BROKER_URL` | Redis DSN for task queue | ✅ |
| `GOOGLE_CUSTOM_SEARCH_API_KEY` | Google CSE API key | ✅ |
| `GOOGLE_SEARCH_ENGINE_ID` | Custom Search Engine ID | ✅ |
| `SENDGRID_API_KEY` | Email delivery | ✅ |
| `STRIPE_SECRET_KEY` | Payment processing | ✅ |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verify | ✅ |
| `SENTRY_DSN` | Error monitoring | Recommended |
| `GOOGLE_REMOVAL_API_KEY` | Auto-removal via Google API | Optional |

---

## Operational SLOs

| Metric | Target |
|--------|--------|
| API availability | 99.9% monthly |
| P95 API latency | < 500ms |
| P99 scan completion | < 5 minutes |
| RTO (recovery time) | < 30 minutes |
| RPO (data loss window) | < 1 hour |
| Deployment frequency | Multiple per day |
| Change failure rate | < 5% |
