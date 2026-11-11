"""
TEE Enclave (Simulated Intel SGX)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Models the Intel SGX enclave in software:
  - MRENCLAVE: SHA-256 of the enclave code (measurement)
  - MRSIGNER:  SHA-256 of the signing key
  - seal_data / unseal_data: AES-GCM encryption bound to the enclave key

In real SGX hardware, these operations occur inside the CPU-protected enclave.
This simulation uses Python's cryptography library to demonstrate the same workflow.
"""

import os
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_KEY_FILE = Path(__file__).parent / ".enclave_key"

# ── Enclave key management ─────────────────────────────────────────

def _get_or_create_enclave_key() -> bytes:
    """
    32-byte AES key. Derives deterministically from ``CORTEX_ENCLAVE_MASTER_KEY``
    when configured (recommended for stateless/containerized deployments), or
    persists a sealed key file to ``.enclave_key`` with owner-only permissions.
    """
    import hashlib

    master = os.getenv("CORTEX_ENCLAVE_MASTER_KEY", "").strip()
    if master:
        return hashlib.sha256(f"cortex-enclave-seal:{master}".encode("utf-8")).digest()

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = os.urandom(32)
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass
    logger.info("[TEE] Enclave key generated and sealed to %s", _KEY_FILE)
    return key


ENCLAVE_KEY = None  # loaded on first access


def _key() -> bytes:
    global ENCLAVE_KEY
    if ENCLAVE_KEY is None:
        ENCLAVE_KEY = _get_or_create_enclave_key()
    return ENCLAVE_KEY


# ── MRENCLAVE measurement ──────────────────────────────────────────

def get_mrenclave() -> str:
    """
    Return the MRENCLAVE — SHA-256 hash of this enclave module's source code.
    In hardware SGX, this is computed by the CPU over the enclave pages.
    """
    try:
        source = Path(__file__).read_bytes()
        return hashlib.sha256(source).hexdigest()
    except Exception:
        return hashlib.sha256(b"cortex-tee-enclave-v1").hexdigest()


def get_mrsigner() -> str:
    """SHA-256 of the enclave signing key (simulated)."""
    return hashlib.sha256(_key()).hexdigest()


# ── seal / unseal ──────────────────────────────────────────────────

def seal_data(plaintext: bytes) -> bytes:
    """
    Encrypt plaintext under the enclave key (AES-256-GCM).
    Returns: nonce (12 bytes) + tag (16 bytes) + ciphertext.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        aesgcm = AESGCM(_key())
        ct = aesgcm.encrypt(nonce, plaintext, b"cortex-tee-v1")
        return nonce + ct          # nonce(12) + tag+ct
    except ImportError:
        # Fallback: XOR with key (for demo only, not secure)
        logger.warning("[TEE] cryptography library not installed — using weak XOR fallback.")
        nonce = os.urandom(12)
        key_cycle = (_key() * ((len(plaintext) // 32) + 1))[:len(plaintext)]
        ct = bytes(a ^ b for a, b in zip(plaintext, key_cycle))
        return nonce + ct


def unseal_data(sealed: bytes) -> bytes:
    """Decrypt sealed data produced by seal_data()."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = sealed[:12]
        ct    = sealed[12:]
        aesgcm = AESGCM(_key())
        return aesgcm.decrypt(nonce, ct, b"cortex-tee-v1")
    except ImportError:
        nonce = sealed[:12]
        ct    = sealed[12:]
        key_cycle = (_key() * ((len(ct) // 32) + 1))[:len(ct)]
        return bytes(a ^ b for a, b in zip(ct, key_cycle))


# ── Enclave status ─────────────────────────────────────────────────

def get_status() -> dict:
    return {
        "running":      True,
        "platform":     "Intel SGX (Simulated)",
        "mode":         os.getenv("TEE_MODE", "simulated"),
        "mrenclave":    get_mrenclave()[:16] + "…",   # truncate for display
        "mrsigner":     get_mrsigner()[:16] + "…",
        "key_loaded":   _KEY_FILE.exists(),
        "api_version":  "1.0.0",
    }
