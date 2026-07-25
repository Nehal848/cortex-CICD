"""
Docker Integration Client
~~~~~~~~~~~~~~~~~~~~~~~~~
Wraps the Docker SDK for Python.
Falls back to mock container data if Docker daemon is not reachable.
"""

import os
import random
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_docker_client = None


def _get_client():
    global _docker_client
    if _docker_client is not None:
        return _docker_client
    try:
        import docker
        host = os.getenv("DOCKER_HOST", "")
        if host:
            client = docker.DockerClient(base_url=host)
        else:
            client = docker.from_env()
        client.ping()
        _docker_client = client
        logger.info("[Docker] Connected to Docker daemon.")
        return client
    except Exception as exc:
        logger.warning("[Docker] Daemon not reachable: %s — using mock.", exc)
        return None


# ── Public API ─────────────────────────────────────────────────────

def list_containers(all_containers: bool = True) -> list[dict]:
    """List containers with name, image, status, ports."""
    client = _get_client()
    if client:
        try:
            containers = client.containers.list(all=all_containers)
            return [_format_container(c) for c in containers]
        except Exception as exc:
            logger.error("[Docker] list_containers error: %s", exc)
    return _mock_containers()


def get_container_stats(container_id: str) -> dict:
    """Return CPU% and memory usage for a container."""
    client = _get_client()
    if client:
        try:
            container = client.containers.get(container_id)
            stats = container.stats(stream=False)
            cpu = _calc_cpu_percent(stats)
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            return {
                "container_id": container_id,
                "cpu_percent": round(cpu, 2),
                "memory_usage_mb": round(mem_usage / 1_048_576, 1),
                "memory_limit_mb": round(mem_limit / 1_048_576, 1),
                "memory_percent": round(mem_usage / mem_limit * 100, 1) if mem_limit else 0,
            }
        except Exception as exc:
            logger.error("[Docker] get_container_stats error: %s", exc)
    return _mock_stats(container_id)


def restart_container(container_id: str) -> dict:
    """Restart a container by ID or name."""
    client = _get_client()
    if client:
        try:
            container = client.containers.get(container_id)
            container.restart(timeout=10)
            return {"success": True, "message": f"Container {container_id} restarted."}
        except Exception as exc:
            logger.error("[Docker] restart_container error: %s", exc)
            return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"[Mock] Container {container_id} restarted.", "mock": True}


def remove_container(container_id: str, force: bool = False) -> dict:
    """Remove a container by ID."""
    client = _get_client()
    if client:
        try:
            container = client.containers.get(container_id)
            container.remove(force=force)
            return {"success": True, "message": f"Container {container_id} removed."}
        except Exception as exc:
            logger.error("[Docker] remove_container error: %s", exc)
            return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"[Mock] Container {container_id} removed.", "mock": True}


def get_summary() -> dict:
    """Return running/stopped/restarting counts."""
    containers = list_containers(all_containers=True)
    running = sum(1 for c in containers if c["status"] == "running")
    stopped = sum(1 for c in containers if c["status"] in ("exited", "stopped"))
    restarting = sum(1 for c in containers if c["status"] == "restarting")
    return {
        "total": len(containers),
        "running": running,
        "stopped": stopped,
        "restarting": restarting,
    }


# ── Helpers ────────────────────────────────────────────────────────

def _format_container(c) -> dict:
    ports = {}
    if c.ports:
        for internal, external in c.ports.items():
            if external:
                ports[internal] = external[0]["HostPort"] if external else None
    return {
        "id": c.short_id,
        "name": c.name,
        "image": c.image.tags[0] if c.image.tags else c.image.short_id,
        "status": c.status,
        "ports": ports,
        "created": c.attrs.get("Created", "")[:19].replace("T", " "),
    }


def _calc_cpu_percent(stats: dict) -> float:
    try:
        cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"]
                     - stats["precpu_stats"]["cpu_usage"]["total_usage"])
        system_delta = (stats["cpu_stats"]["system_cpu_usage"]
                        - stats["precpu_stats"]["system_cpu_usage"])
        num_cpus = stats["cpu_stats"]["online_cpus"]
        if system_delta > 0:
            return (cpu_delta / system_delta) * num_cpus * 100.0
    except (KeyError, ZeroDivisionError):
        pass
    return 0.0


# ── Mock data ──────────────────────────────────────────────────────

_MOCK_CONTAINERS = [
    {"id": "a1b2c3d4", "name": "cortex-api",         "image": "cortex-api:v2.4.1",     "status": "running",    "ports": {"5000/tcp": "5000"}, "created": "2026-07-25 06:00:00"},
    {"id": "e5f6a7b8", "name": "cortex-ui",          "image": "cortex-ui:v2.4.1",      "status": "running",    "ports": {"80/tcp": "8080"},   "created": "2026-07-25 06:02:00"},
    {"id": "c9d0e1f2", "name": "healing-agent",      "image": "healing-agent:v1.0.4",  "status": "running",    "ports": {},                   "created": "2026-07-25 05:00:00"},
    {"id": "g3h4i5j6", "name": "ml-predictor",       "image": "ml-predictor:v0.9.2",   "status": "running",    "ports": {"8000/tcp": "8000"}, "created": "2026-07-24 18:00:00"},
    {"id": "k7l8m9n0", "name": "prometheus",         "image": "prom/prometheus:latest", "status": "running",   "ports": {"9090/tcp": "9090"}, "created": "2026-07-24 12:00:00"},
    {"id": "o1p2q3r4", "name": "grafana",            "image": "grafana/grafana:latest", "status": "running",   "ports": {"3000/tcp": "3000"}, "created": "2026-07-24 12:00:00"},
    {"id": "s5t6u7v8", "name": "redis",              "image": "redis:alpine",           "status": "running",   "ports": {"6379/tcp": "6379"}, "created": "2026-07-24 12:00:00"},
    {"id": "w9x0y1z2", "name": "cortex-worker",      "image": "cortex-worker:v2.5.0-rc1","status": "exited",  "ports": {},                   "created": "2026-07-24 10:00:00"},
    {"id": "a3b4c5d6", "name": "jenkins",            "image": "jenkins/jenkins:lts",   "status": "running",    "ports": {"8080/tcp": "8080"}, "created": "2026-07-23 08:00:00"},
    {"id": "e7f8g9h0", "name": "postgres-main",      "image": "postgres:16.3",         "status": "running",    "ports": {"5432/tcp": "5432"}, "created": "2026-07-23 08:00:00"},
]


def _mock_containers() -> list[dict]:
    return _MOCK_CONTAINERS


def _mock_stats(container_id: str) -> dict:
    return {
        "container_id": container_id,
        "cpu_percent": round(random.uniform(5, 45), 2),
        "memory_usage_mb": round(random.uniform(128, 512), 1),
        "memory_limit_mb": 1024.0,
        "memory_percent": round(random.uniform(12, 50), 1),
    }
