"""
Prometheus Integration Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Queries the Prometheus HTTP API for real metrics.
Falls back to simulated oscillating values if Prometheus is not reachable.
"""

import os
import random
import logging
import time
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

logger = logging.getLogger(__name__)

_PROM_URL = None
_last_check = 0
_prom_available = None


def _base_url() -> str:
    global _PROM_URL, _last_check
    db_url = None
    try:
        from app.models import PlatformSetting
        db_url = PlatformSetting.get_value("prometheus_url")
    except Exception:
        db_url = None

    resolved = (db_url or os.getenv("PROMETHEUS_URL", "http://localhost:9090")).rstrip("/")
    if resolved != _PROM_URL:
        _PROM_URL = resolved
        _last_check = 0  # re-probe when URL changes
    return _PROM_URL


def _is_available() -> bool:
    """Check connectivity with a 10-second cache."""
    global _prom_available, _last_check
    if time.time() - _last_check < 10:
        return _prom_available
    try:
        req = Request(f"{_base_url()}/-/healthy", headers={"Accept": "text/plain"})
        with urlopen(req, timeout=2) as resp:
            _prom_available = resp.status == 200
    except Exception:
        _prom_available = False
    _last_check = time.time()
    return _prom_available


def _query(promql: str) -> float | None:
    """Run an instant query and return the scalar result."""
    try:
        from urllib.parse import urlencode, quote
        url = f"{_base_url()}/api/v1/query?query={quote(promql)}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=3) as resp:
            data = json.load(resp)
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
    except Exception as exc:
        logger.debug("[Prometheus] query error: %s", exc)
    return None


# ── Public API ─────────────────────────────────────────────────────

def get_cpu_usage() -> float:
    """Return current CPU usage as a percentage (0-100)."""
    if _is_available():
        val = _query('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)')
        if val is not None:
            return round(val, 1)
    return _simulated_cpu()


def get_memory_usage() -> float:
    """Return memory usage as a percentage (0-100)."""
    if _is_available():
        val = _query(
            '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))'
        )
        if val is not None:
            return round(val, 1)
    return _simulated_memory()


def get_disk_usage() -> float:
    """Return disk usage as a percentage (0-100)."""
    if _is_available():
        val = _query(
            '100 * (1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}))'
        )
        if val is not None:
            return round(val, 1)
    return _simulated_disk()


def get_network_io() -> dict:
    """Return network bytes received/transmitted per second."""
    if _is_available():
        rx = _query('sum(rate(node_network_receive_bytes_total[1m]))')
        tx = _query('sum(rate(node_network_transmit_bytes_total[1m]))')
        if rx is not None and tx is not None:
            return {
                "rx_bytes_per_sec": round(rx, 0),
                "tx_bytes_per_sec": round(tx, 0),
                "rx_mb_per_sec": round(rx / 1_048_576, 2),
                "tx_mb_per_sec": round(tx / 1_048_576, 2),
            }
    return _simulated_network()


def get_all_metrics() -> dict:
    """Return all metrics in a single call."""
    return {
        "cpu_percent": get_cpu_usage(),
        "memory_percent": get_memory_usage(),
        "disk_percent": get_disk_usage(),
        "network": get_network_io(),
        "source": "prometheus" if _is_available() else "simulated",
    }


def get_http_request_rate() -> float:
    """HTTP requests per second hitting the cortex-api."""
    if _is_available():
        val = _query('sum(rate(flask_http_request_total[1m]))')
        if val is not None:
            return round(val, 2)
    return round(random.uniform(8, 35), 2)


def get_error_rate() -> float:
    """Percentage of HTTP responses that are 5xx errors."""
    if _is_available():
        val = _query(
            '100 * sum(rate(flask_http_request_total{status=~"5.."}[1m])) / sum(rate(flask_http_request_total[1m]))'
        )
        if val is not None:
            return round(val, 2)
    return round(random.uniform(0.1, 2.5), 2)


# ── Simulated oscillators ──────────────────────────────────────────

_sim_cpu    = 65.0
_sim_memory = 58.0
_sim_disk   = 42.0


def _simulated_cpu() -> float:
    global _sim_cpu
    _sim_cpu = max(40.0, min(85.0, _sim_cpu + random.uniform(-3, 3)))
    return round(_sim_cpu, 1)


def _simulated_memory() -> float:
    global _sim_memory
    _sim_memory = max(45.0, min(75.0, _sim_memory + random.uniform(-2, 2)))
    return round(_sim_memory, 1)


def _simulated_disk() -> float:
    global _sim_disk
    _sim_disk = max(35.0, min(55.0, _sim_disk + random.uniform(-0.5, 0.5)))
    return round(_sim_disk, 1)


def _simulated_network() -> dict:
    rx = random.uniform(500_000, 5_000_000)
    tx = random.uniform(200_000, 2_000_000)
    return {
        "rx_bytes_per_sec": round(rx, 0),
        "tx_bytes_per_sec": round(tx, 0),
        "rx_mb_per_sec": round(rx / 1_048_576, 2),
        "tx_mb_per_sec": round(tx / 1_048_576, 2),
    }
