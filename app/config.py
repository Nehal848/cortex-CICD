import os
from datetime import timedelta

class Config:
    ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-default-key")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///cortex.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
    JENKINS_URL = os.getenv("JENKINS_URL", "http://localhost:8080")
    JENKINS_USER = os.getenv("JENKINS_USER", "admin")
    JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "")
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    TEE_MODE = os.getenv("TEE_MODE", "simulated")
    GITHUB_WEBHOOK_SECRET  = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    JENKINS_WEBHOOK_SECRET = os.getenv("JENKINS_WEBHOOK_SECRET", "")
    ALERTMANAGER_TOKEN     = os.getenv("ALERTMANAGER_TOKEN", "")
    CORTEX_API_TOKEN       = os.getenv("CORTEX_API_TOKEN", "")
    REDIS_URL              = os.getenv("REDIS_URL", "")
    TRUSTED_PROXY_COUNT    = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
    STRICT_WEBHOOK_VERIFICATION = os.getenv("STRICT_WEBHOOK_VERIFICATION", "false").lower() in ("true", "1")

    # Security & Cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    @classmethod
    def validate_production_security(cls):
        """Refuse boot in production if default or weak credentials remain."""
        import logging
        env_val = cls.ENV if cls.ENV != "development" else os.getenv("FLASK_ENV", cls.ENV)
        if env_val == "production":
            secret_val = (
                cls.SECRET_KEY
                if cls.SECRET_KEY != "super-secret-default-key"
                else os.getenv("SECRET_KEY", cls.SECRET_KEY)
            )
            admin_pw = (
                cls.ADMIN_PASSWORD
                if cls.ADMIN_PASSWORD != "admin"
                else os.getenv("ADMIN_PASSWORD", cls.ADMIN_PASSWORD)
            )
            insecure_keys = {
                "super-secret-default-key",
                "cortex-secret-key-change-in-production",
                "test-secret",
                ""
            }
            if secret_val in insecure_keys or len(secret_val) < 16:
                raise RuntimeError(
                    "[SECURITY VIOLATION] Cortex cannot boot in production mode with a default, short, or empty SECRET_KEY. "
                    "Set a secure, random SECRET_KEY environment variable."
                )

            insecure_passwords = {"admin", "admin123", "password", "root", ""}
            if admin_pw in insecure_passwords:
                raise RuntimeError(
                    "[SECURITY VIOLATION] Cortex cannot boot in production mode with a default ADMIN_PASSWORD. "
                    "Set a strong ADMIN_PASSWORD environment variable."
                )

            _log = logging.getLogger("cortex.security")
            for optional_prod_secret in (
                "GITHUB_WEBHOOK_SECRET",
                "JENKINS_WEBHOOK_SECRET",
                "ALERTMANAGER_TOKEN",
                "CORTEX_ENCLAVE_MASTER_KEY",
            ):
                if not os.getenv(optional_prod_secret):
                    _log.warning(
                        "[SECURITY WARNING] %s is unset in production — related endpoints/sealing will fail closed or use ephemeral local key.",
                        optional_prod_secret,
                    )

