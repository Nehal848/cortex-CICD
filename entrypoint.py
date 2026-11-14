#!/usr/bin/env python3
"""
entrypoint.py — Cortex API startup script.

Ensures the ML model is present before Gunicorn starts.
If ml/models/failure_predictor.pkl is missing (first boot or fresh clone),
the model is trained on synthetic data so the app starts successfully.

Usage (in Dockerfile CMD or docker-compose command):
    python entrypoint.py
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("cortex.entrypoint")

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml", "models", "failure_predictor.pkl")


def _ensure_model() -> None:
    if os.path.exists(MODEL_PATH):
        log.info("ML model already present at %s", MODEL_PATH)
        return

    log.info("ML model not found — training initial model on synthetic data …")
    try:
        # ml/predict_failure.py exposes a module-level train helper
        sys.path.insert(0, os.path.dirname(__file__))
        from ml.predict_failure import FailurePredictor  # type: ignore

        predictor = FailurePredictor()
        predictor._train()
        log.info("ML model trained and saved to %s", MODEL_PATH)
    except Exception as exc:  # pragma: no cover
        log.warning("Could not pre-train model (non-fatal): %s", exc)
        log.warning("The app will start but /api/predict may return mock results.")


def _start_gunicorn() -> None:
    import subprocess

    workers = os.getenv("GUNICORN_WORKERS", "2")
    threads = os.getenv("GUNICORN_THREADS", "4")
    timeout = os.getenv("GUNICORN_TIMEOUT", "120")
    bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")

    cmd = [
        "gunicorn",
        "--worker-class", "gthread",
        "--threads", threads,
        "--workers", workers,
        "--timeout", timeout,
        "-b", bind,
        "wsgi:application",
    ]
    log.info("Starting Gunicorn: %s", " ".join(cmd))
    os.execvp(cmd[0], cmd)  # replace this process — signals pass through cleanly


if __name__ == "__main__":
    _ensure_model()
    _start_gunicorn()
