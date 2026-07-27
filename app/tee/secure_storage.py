"""
TEE Secure Storage
~~~~~~~~~~~~~~~~~~~
Encrypted key-value store backed by the enclave sealing key.
All secrets are AES-256-GCM encrypted before being written to disk.
The storage file is at TEE_SECRETS_PATH (default: tee/secrets.enc).
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STORAGE_PATH = Path(os.getenv("TEE_SECRETS_PATH", "tee/secrets.enc"))


def _load_store() -> dict:
    """Load and decrypt the entire secret store from disk."""
    if not _STORAGE_PATH.exists():
        return {}
    try:
        from . import enclave
        sealed = _STORAGE_PATH.read_bytes()
        plain  = enclave.unseal_data(sealed)
        return json.loads(plain.decode("utf-8"))
    except Exception as exc:
        logger.error("[SecureStorage] Failed to load store: %s", exc)
        return {}


def _save_store(store: dict) -> None:
    """Encrypt and persist the secret store to disk."""
    try:
        from . import enclave
        plain  = json.dumps(store).encode("utf-8")
        sealed = enclave.seal_data(plain)
        _STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORAGE_PATH.write_bytes(sealed)
    except Exception as exc:
        logger.error("[SecureStorage] Failed to save store: %s", exc)


# ── Public API ─────────────────────────────────────────────────────

def store_secret(key: str, value: str) -> bool:
    """Seal and store a secret by key. Returns True on success."""
    try:
        store = _load_store()
        store[key] = value
        _save_store(store)
        logger.info("[SecureStorage] Secret '%s' stored.", key)
        return True
    except Exception as exc:
        logger.error("[SecureStorage] store_secret error: %s", exc)
        return False


def retrieve_secret(key: str, default: str = "") -> str:
    """Retrieve and unseal a secret by key."""
    try:
        store = _load_store()
        return store.get(key, default)
    except Exception as exc:
        logger.error("[SecureStorage] retrieve_secret error: %s", exc)
        return default


def delete_secret(key: str) -> bool:
    """Remove a secret from the store."""
    try:
        store = _load_store()
        if key in store:
            del store[key]
            _save_store(store)
            logger.info("[SecureStorage] Secret '%s' deleted.", key)
            return True
        return False
    except Exception as exc:
        logger.error("[SecureStorage] delete_secret error: %s", exc)
        return False


def list_secret_keys() -> list[str]:
    """Return the list of secret keys (NOT values)."""
    try:
        return list(_load_store().keys())
    except Exception:
        return []


def get_store_info() -> dict:
    """Return metadata about the secret store."""
    keys = list_secret_keys()
    return {
        "path":         str(_STORAGE_PATH),
        "exists":       _STORAGE_PATH.exists(),
        "secret_count": len(keys),
        "keys":         keys,
        "encrypted":    True,
        "algorithm":    "AES-256-GCM",
    }
