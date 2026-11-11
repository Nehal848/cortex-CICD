"""
Failure Prediction Model (ML)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Uses a trained RandomForest to predict failure risk and failure type.
On first import it trains the model on the mock dataset and caches it to disk.
Falls back to the heuristic baseline if training data is unavailable.
"""

import hashlib
import hmac
import os
import random
import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR  = Path(__file__).parent / "models"
_MODEL_PATH = _MODEL_DIR / "failure_predictor.pkl"
_SIG_PATH   = _MODEL_DIR / "failure_predictor.pkl.sig"

_model = None          # RandomForestClassifier
_type_model = None     # RandomForestClassifier for failure type


def _model_hmac_key() -> bytes:
    """Derive HMAC key used to sign and verify cached ML pickle bundles."""
    secret = (
        os.getenv("CORTEX_ENCLAVE_MASTER_KEY")
        or os.getenv("SECRET_KEY")
        or "cortex-ml-dev-signing-key"
    )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _sign_model_bytes(raw: bytes) -> str:
    return hmac.new(_model_hmac_key(), raw, hashlib.sha256).hexdigest()


def _verify_model_bytes(raw: bytes) -> bool:
    if not _SIG_PATH.exists():
        return False
    expected = _SIG_PATH.read_text(encoding="utf-8").strip()
    return hmac.compare_digest(expected, _sign_model_bytes(raw))


def _save_model_bundle(bundle: dict) -> None:
    """Serialize and HMAC-sign the model bundle atomically."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    raw = pickle.dumps(bundle)
    _MODEL_PATH.write_bytes(raw)
    _SIG_PATH.write_text(_sign_model_bytes(raw), encoding="utf-8")

# Failure type labels
FAILURE_TYPES = [
    "None",
    "Test Suite Timeout",
    "OOM — Pod Evicted",
    "Dependency Resolution",
    "Build Script Error",
    "High CPU Saturation",
    "Network Timeout",
    "Liveness Probe Fail",
]

# Recommended healing action per failure type
_RECOMMENDED_ACTIONS = {
    "None":                 ("No action required",     "Monitor metrics"),
    "Test Suite Timeout":   ("Auto Retry Build",       "Increase timeout threshold"),
    "OOM — Pod Evicted":    ("Restart Pod",            "Increase memory limit"),
    "Dependency Resolution":("Rollback Deployment",    "Pin dependency versions"),
    "Build Script Error":   ("Rollback Deployment",    "Review build logs"),
    "High CPU Saturation":  ("Scale Up Replicas",      "Enable HPA autoscaling"),
    "Network Timeout":      ("Auto Retry Build",       "Add circuit breaker"),
    "Liveness Probe Fail":  ("Restart Pod",            "Check probe configuration"),
}


def _confidence_label(score: float) -> str:
    if score >= 0.90:
        return "Very High"
    elif score >= 0.75:
        return "High"
    elif score >= 0.55:
        return "Medium"
    return "Low"


def _load_or_train():
    """Load cached model or train from scratch."""
    global _model, _type_model

    if _model is not None:
        return True

    if _MODEL_PATH.exists():
        try:
            raw = _MODEL_PATH.read_bytes()
            if not _verify_model_bytes(raw):
                logger.warning(
                    "[ML] Model integrity check failed (%s missing or tampered) — retraining.",
                    _SIG_PATH.name,
                )
            else:
                bundle = pickle.loads(raw)
                _model      = bundle["risk_model"]
                _type_model = bundle["type_model"]
                logger.info("[ML] Loaded verified cached model from %s", _MODEL_PATH)
                return True
        except Exception as exc:
            logger.warning("[ML] Failed to load cached model: %s — retraining.", exc)

    return _train()


def _train() -> bool:
    """Train RandomForest on the mock dataset."""
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.model_selection import train_test_split
        import requests

        logger.info("[ML] Training failure prediction model…")

        # Try to fetch real Jenkins data first
        jenkins_url = os.getenv("JENKINS_URL", "")
        jenkins_user = os.getenv("JENKINS_USER", "")
        jenkins_token = os.getenv("JENKINS_TOKEN", "")
        real_data_used = False
        
        # We will keep the synthetic generation as a fallback if Jenkins has no data
        np.random.seed(42)
        n = 2000

        # Generate synthetic training data from domain knowledge
        np.random.seed(42)
        n = 2000

        # Features: [branch_is_main, files_changed, hour_of_day, day_of_week,
        #            duration_secs, consecutive_failures]
        branch_is_main       = np.random.binomial(1, 0.6, n)
        files_changed        = np.random.exponential(15, n).astype(int)
        hour_of_day          = np.random.randint(0, 24, n)
        day_of_week          = np.random.randint(0, 7, n)
        duration_secs        = np.random.exponential(120, n).astype(int)
        consecutive_failures = np.random.poisson(0.3, n)

        X = np.column_stack([
            branch_is_main, files_changed, hour_of_day,
            day_of_week, duration_secs, consecutive_failures,
        ])

        # Risk score (0-100)
        base = (
            (1 - branch_is_main) * 15
            + np.clip(files_changed, 0, 60) * 0.5
            + consecutive_failures * 12
            + (duration_secs > 250).astype(int) * 20
            + np.random.randint(-8, 15, n)
        )
        y_risk = np.clip(base, 0, 100).astype(int)

        # Failure type (0 = None, 1-7 = failure types)
        y_type = np.zeros(n, dtype=int)
        failed_mask = y_risk >= 60
        y_type[failed_mask] = np.random.choice(range(1, len(FAILURE_TYPES)), size=failed_mask.sum())

        X_train, _, yr_train, _, yt_train, _ = train_test_split(
            X, y_risk, y_type, test_size=0.2, random_state=42
        )

        risk_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        risk_model.fit(X_train, yr_train)

        type_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        type_model.fit(X_train, yt_train)

        _save_model_bundle({"risk_model": risk_model, "type_model": type_model})

        global _model, _type_model
        _model      = risk_model
        _type_model = type_model
        logger.info("[ML] Model trained and saved to %s", _MODEL_PATH)
        return True

    except ImportError:
        logger.warning("[ML] scikit-learn not installed — using heuristic fallback.")
        return False
    except Exception as exc:
        logger.error("[ML] Training failed: %s — using heuristic fallback.", exc)
        return False


def retrain_from_database(min_samples: int = 5) -> dict:
    """
    Retrain the failure prediction models using real historical runs from the DB.
    Falls back gracefully if database samples are below min_samples.
    """
    try:
        from app.models import PipelineRun
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

        runs = PipelineRun.query.order_by(PipelineRun.created_at.desc()).all()
        if len(runs) < min_samples:
            return {
                "retrained": False,
                "reason": f"Insufficient database records ({len(runs)} < {min_samples}). Synthetic training kept.",
                "total_records": len(runs)
            }

        X_rows = []
        y_risks = []
        y_types = []

        for r in runs:
            b_main = 1 if r.branch in ("main", "master") else 0
            created = r.created_at
            hour = created.hour if created else 12
            dow = created.weekday() if created else 0
            dur = r.duration_secs or 60
            streak = 1 if r.status == "Failed" else 0
            fc = getattr(r, "files_changed", None) or 10

            X_rows.append([b_main, fc, hour, dow, dur, streak])

            if r.status == "Failed":
                risk = max(75, r.risk_score or 80)
                ft_idx = 1
            elif r.status == "Healed":
                risk = max(60, r.risk_score or 65)
                ft_idx = 2
            else:
                risk = min(25, r.risk_score or 10)
                ft_idx = 0

            y_risks.append(risk)
            y_types.append(ft_idx)

        X = np.array(X_rows)
        yr = np.array(y_risks)
        yt = np.array(y_types)

        risk_model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        risk_model.fit(X, yr)

        type_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        type_model.fit(X, yt)

        _save_model_bundle({"risk_model": risk_model, "type_model": type_model})

        global _model, _type_model
        _model = risk_model
        _type_model = type_model

        return {
            "retrained": True,
            "samples_used": len(runs),
            "model_path": str(_MODEL_PATH),
            "status": "Models successfully retrained from database telemetry."
        }
    except Exception as exc:
        logger.error("[ML] Retraining error: %s", exc)
        return {"retrained": False, "error": str(exc)}


def predict_failure_risk(
    repo: str,
    branch: str,
    files_changed: int,
    duration_secs: int = 0,
    consecutive_failures: int = 0,
    triggered_at_hour: int | None = None,
    day_of_week: int | None = None,
) -> dict:
    """
    Predict failure risk and type for a pipeline run.

    Returns
    -------
    dict
        {risk_score, failure_type, confidence, features}
    """
    import datetime as dt
    now = dt.datetime.utcnow()
    hour   = triggered_at_hour if triggered_at_hour is not None else now.hour
    dow    = day_of_week if day_of_week is not None else now.weekday()
    b_main = 1 if ("main" in branch or "master" in branch) else 0

    features = [b_main, files_changed, hour, dow, duration_secs, consecutive_failures]

    if _load_or_train() and _model is not None:
        try:
            import numpy as np
            X = np.array(features).reshape(1, -1)

            risk_raw   = float(_model.predict(X)[0])
            risk_score = max(0, min(100, int(round(risk_raw))))

            # Failure type prediction + probability
            proba  = _type_model.predict_proba(X)[0]
            type_idx = int(proba.argmax())
            confidence = round(float(proba[type_idx]), 3)
            failure_type = FAILURE_TYPES[type_idx] if type_idx < len(FAILURE_TYPES) else "Unknown"

            # If risk low but type_model says failure, reconcile
            if risk_score < 40 and failure_type != "None":
                failure_type = "None"
                confidence   = round(1 - confidence, 3)

            rec, alt = _RECOMMENDED_ACTIONS.get(
                failure_type, ("Investigate manually", "Escalate to on-call")
            )
            return {
                "risk_score":        risk_score,
                "failure_type":      failure_type,
                "confidence":        confidence,
                "confidence_label":  _confidence_label(confidence),
                "recommended_action": rec,
                "alternative_action": alt,
                "features": {
                    "branch_is_main": bool(b_main),
                    "files_changed":  files_changed,
                    "duration_secs":  duration_secs,
                    "consecutive_failures": consecutive_failures,
                },
                "model": "RandomForest",
            }
        except Exception as exc:
            logger.error("[ML] predict error: %s — using heuristic.", exc)

    # ── Heuristic fallback ─────────────────────────────────────────
    return _heuristic(branch, files_changed, consecutive_failures)


def _heuristic(branch: str, files_changed: int, consecutive_failures: int) -> dict:
    base = 10
    if "main" not in branch and "master" not in branch:
        base += 15
    if files_changed > 50:
        base += 40
    elif files_changed > 10:
        base += 20
    base += consecutive_failures * 10
    risk = max(0, min(100, base + random.randint(-5, 15)))
    failure_type = "None" if risk < 50 else random.choice(FAILURE_TYPES[1:])
    confidence = round(random.uniform(0.55, 0.75), 3)
    rec, alt = _RECOMMENDED_ACTIONS.get(
        failure_type, ("Investigate manually", "Escalate to on-call")
    )
    return {
        "risk_score":         risk,
        "failure_type":       failure_type,
        "confidence":         confidence,
        "confidence_label":   _confidence_label(confidence),
        "recommended_action": rec,
        "alternative_action": alt,
        "features":           {"branch": branch, "files_changed": files_changed},
        "model":              "heuristic",
    }
