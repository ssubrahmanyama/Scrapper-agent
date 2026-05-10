"""
services/secrets/vault_loader.py
OSS replacement for AWS Secrets Manager.

Uses HashiCorp Vault OSS (MPL-2.0, versions ≤ 1.13) or OpenBao (MPL-2.0 fork).
Vault runs as a container in docker-compose and Kubernetes.
Secrets are written once via `vault kv put secret/privacyshield/production key=val`.
"""
from __future__ import annotations

import os

import hvac
import structlog

logger = structlog.get_logger(__name__)

VAULT_ADDR   = os.getenv("VAULT_ADDR",         "http://vault:8200")
VAULT_TOKEN  = os.getenv("VAULT_TOKEN",         "")
VAULT_PATH   = os.getenv("VAULT_SECRET_PATH",   "privacyshield/production")


def load_vault_secrets() -> None:
    """
    Pull secrets from Vault KV-v2 and inject into os.environ.
    Call this BEFORE constructing Settings() in main.py startup.
    Silently skips if VAULT_TOKEN is empty (pure-env-var dev mode).
    """
    if not VAULT_TOKEN:
        logger.debug("VAULT_TOKEN not set — using raw environment variables")
        return

    try:
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        if not client.is_authenticated():
            logger.warning("Vault token invalid — falling back to env vars")
            return

        resp = client.secrets.kv.v2.read_secret_version(path=VAULT_PATH, raise_on_deleted_version=True)
        secrets: dict = resp["data"]["data"]

        injected = 0
        for k, v in secrets.items():
            os.environ.setdefault(k, str(v))   # env var wins if already set
            injected += 1

        logger.info("Vault secrets loaded", count=injected, path=VAULT_PATH)

    except Exception as exc:
        logger.warning("Vault unavailable — continuing with env vars", error=str(exc))
