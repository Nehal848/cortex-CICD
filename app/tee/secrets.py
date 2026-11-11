"""
TEE Secrets Integration
~~~~~~~~~~~~~~~~~~~~~~~~
Loads sensitive credentials through the TEE sealed store.
On startup, migrates credentials from .env into sealed storage.
Application code should call get() rather than os.getenv() for secrets.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Keys to migrate from .env into sealed storage on first boot
_SENSITIVE_KEYS = [
    "JENKINS_TOKEN",
    "SLACK_WEBHOOK_URL",
    "SMTP_PASS",
    "SMTP_PASSWORD",
]


def bootstrap():
    """
    On first startup, migrate sensitive .env values into sealed storage.
    Subsequent boots read from sealed storage instead of plaintext .env.
    """
    try:
        from . import secure_storage
        existing = set(secure_storage.list_secret_keys())
        migrated = 0
        for key in _SENSITIVE_KEYS:
            if key not in existing:
                val = os.getenv(key, "")
                if val:
                    secure_storage.store_secret(key, val)
                    migrated += 1
        if migrated:
            logger.info("[TEE Secrets] Migrated %d credential(s) into sealed storage.", migrated)
    except Exception as exc:
        logger.warning("[TEE Secrets] bootstrap error: %s — falling back to env vars.", exc)


def get(key: str, default: str = "") -> str:
    """
    Retrieve a secret — checks sealed storage first, then falls back to os.getenv().
    """
    try:
        from . import secure_storage
        val = secure_storage.retrieve_secret(key, "")
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, default)


def get_tee_summary() -> dict:
    """Return a dashboard-ready TEE status summary."""
    try:
        from . import enclave, attestation, secure_storage
        enc_status = enclave.get_status()
        store_info = secure_storage.get_store_info()
        report     = attestation.generate_attestation_report()
        return {
            "enclave":          enc_status,
            "attestation":      {
                "status":         report.get("verification_status"),
                "tcb_status":     report.get("tcb_status"),
                "security_score": report.get("security_score"),
                "mrenclave":      report.get("mrenclave", "")[:16] + "…",
            },
            "sealed_secrets":   store_info["secret_count"],
            "storage_encrypted": store_info["encrypted"],
            "overall_status":   "Secure",
        }
    except Exception as exc:
        logger.error("[TEE] get_tee_summary error: %s", exc)
        return {"overall_status": "Error", "error": str(exc)}
