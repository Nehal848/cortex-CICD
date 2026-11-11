"""
Jenkins Integration Client
~~~~~~~~~~~~~~~~~~~~~~~~~~
Wraps the Jenkins REST API (python-jenkins library).
Falls back to realistic mock data if JENKINS_URL is not set or Jenkins is unreachable.
"""

import os
import random
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_jenkins_instance = None
_jenkins_url_cached = None


def _get_client():
    """Lazily initialise the python-jenkins client, respecting PlatformSetting updates."""
    global _jenkins_instance, _jenkins_url_cached

    db_url = None
    try:
        from app.models import PlatformSetting
        db_url = PlatformSetting.get_value("jenkins_url")
    except Exception:
        db_url = None

    url = (db_url or os.getenv("JENKINS_URL", "")).strip()
    user = os.getenv("JENKINS_USER", "")
    token = os.getenv("JENKINS_TOKEN", "")

    if _jenkins_instance is not None and _jenkins_url_cached == url:
        return _jenkins_instance

    if not url or not token:
        _jenkins_instance = None
        _jenkins_url_cached = None
        logger.info("[Jenkins] No credentials configured — using mock mode.")
        return None

    try:
        import jenkins  # python-jenkins
        server = jenkins.Jenkins(url, username=user, password=token)
        server.get_whoami()          # validate credentials
        _jenkins_instance = server
        _jenkins_url_cached = url
        logger.info("[Jenkins] Connected to %s", url)
        return server
    except Exception as exc:
        logger.warning("[Jenkins] Could not connect: %s — falling back to mock.", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────

def get_all_jobs() -> list[dict]:
    """Return list of Jenkins jobs with latest build info."""
    client = _get_client()
    if client:
        try:
            jobs = client.get_all_jobs()
            result = []
            for j in jobs:
                name = j["fullname"]
                try:
                    info = client.get_job_info(name)
                    lb = info.get("lastBuild") or {}
                    result.append({
                        "name": name,
                        "url": info.get("url", ""),
                        "last_build_number": lb.get("number"),
                        "last_build_result": lb.get("result", "UNKNOWN"),
                        "last_build_url": lb.get("url", ""),
                    })
                except Exception:
                    result.append({"name": name, "url": j.get("url", ""), "last_build_number": None,
                                   "last_build_result": "UNKNOWN", "last_build_url": ""})
            return result
        except Exception as exc:
            logger.error("[Jenkins] get_all_jobs error: %s", exc)

    return _mock_jobs()


def get_build_status(job_name: str, build_number: int) -> dict:
    """Return status/duration/result of a specific build."""
    client = _get_client()
    if client:
        try:
            info = client.get_build_info(job_name, build_number)
            return {
                "number": info["number"],
                "result": info.get("result") or "IN_PROGRESS",
                "duration_ms": info.get("duration", 0),
                "timestamp": info.get("timestamp", 0),
                "url": info.get("url", ""),
                "building": info.get("building", False),
            }
        except Exception as exc:
            logger.error("[Jenkins] get_build_status error: %s", exc)

    return _mock_build_status(build_number)


def get_console_log(job_name: str, build_number: int) -> str:
    """Return console output of a build."""
    client = _get_client()
    if client:
        try:
            return client.get_build_console_output(job_name, build_number)
        except Exception as exc:
            logger.error("[Jenkins] get_console_log error: %s", exc)

    return _mock_console_log()


def trigger_build(job_name: str, parameters: dict | None = None) -> dict:
    """Trigger a new Jenkins build."""
    client = _get_client()
    if client:
        try:
            if parameters:
                client.build_job(job_name, parameters=parameters)
            else:
                client.build_job(job_name)
            return {"success": True, "message": f"Build triggered for {job_name}"}
        except Exception as exc:
            logger.error("[Jenkins] trigger_build error: %s", exc)
            return {"success": False, "message": str(exc)}

    # Mock: simulate a trigger
    return {"success": True, "message": f"[Mock] Build triggered for {job_name}", "mock": True}


# ── Mock data ──────────────────────────────────────────────────────

def _mock_jobs() -> list[dict]:
    statuses = ["SUCCESS", "FAILURE", "UNSTABLE", "SUCCESS", "SUCCESS", "ABORTED"]
    jobs = [
        "CortexCICD/Self-Healing-CI-CD",
        "CortexCICD/ML-Predictor",
        "CortexCICD/cortex-api",
        "CortexCICD/cortex-ui",
        "CortexCICD/healing-agent",
    ]
    return [
        {
            "name": name,
            "url": f"http://localhost:8080/job/{name.replace('/', '/job/')}/",
            "last_build_number": random.randint(80, 150),
            "last_build_result": random.choice(statuses),
            "last_build_url": f"http://localhost:8080/job/{name}/lastBuild/",
        }
        for name in jobs
    ]


def _mock_build_status(build_number: int) -> dict:
    results = ["SUCCESS", "FAILURE", "UNSTABLE", "SUCCESS", "SUCCESS"]
    return {
        "number": build_number,
        "result": random.choice(results),
        "duration_ms": random.randint(30_000, 300_000),
        "timestamp": int((datetime.utcnow() - timedelta(minutes=random.randint(5, 120))).timestamp() * 1000),
        "url": f"http://localhost:8080/job/CortexCICD/{build_number}/",
        "building": False,
    }


def _mock_console_log() -> str:
    return (
        "[Pipeline] Start of Pipeline\n"
        "[Pipeline] stage (Checkout)\n"
        "[Pipeline] { (Checkout)\n"
        "[Pipeline] checkout\n"
        "Cloning repository https://github.com/CortexCICD/Self-Healing-CI-CD\n"
        "[Pipeline] stage (Build)\n"
        "Running make build...\n"
        "Successfully built docker image cortex-api:latest\n"
        "[Pipeline] stage (Test)\n"
        "Running pytest tests/ ...\n"
        "15 passed, 0 failed in 12.4s\n"
        "[Pipeline] stage (Deploy)\n"
        "Applying kubernetes/deployment.yaml\n"
        "deployment.apps/cortex-api configured\n"
        "[Pipeline] End of Pipeline\n"
        "Finished: SUCCESS\n"
    )
