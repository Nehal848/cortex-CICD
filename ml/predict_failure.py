"""
Failure Prediction Model (ML)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Uses a trained RandomForest to predict failure risk and failure type.
On first import it trains the model on the mock dataset and caches it to disk.
Falls back to the heuristic baseline if training data is unavailable.
"""

import os
import random
import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR  = Path(__file__).parent / "models"
_MODEL_PATH = _MODEL_DIR / "failure_predictor.pkl"

_model = None          # RandomForestClassifier
_type_model = None     # RandomForestClassifier for failure type

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
            with open(_MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)
            _model      = bundle["risk_model"]
            _type_model = bundle["type_model"]
            logger.info("[ML] Loaded cached model from %s", _MODEL_PATH)
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

        logger.info("[ML] Training failure prediction model…")

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

        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"risk_model": risk_model, "type_model": type_model}, f)

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
