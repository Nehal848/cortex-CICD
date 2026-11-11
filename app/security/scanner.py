"""
Trivy Image Scanner
~~~~~~~~~~~~~~~~~~~~
Wraps the Trivy CLI to scan Docker images for CVEs.
Falls back to mock scan results if Trivy is not installed.
"""

import os
import json
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def _trivy_path() -> str:
    return os.getenv("TRIVY_PATH", "trivy")


def _trivy_available() -> bool:
    try:
        result = subprocess.run(
            [_trivy_path(), "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def scan_image(image_name: str) -> dict:
    """
    Scan a Docker image for vulnerabilities using Trivy.

    Returns
    -------
    dict
        {image, critical, high, medium, low, total, vulnerabilities, scan_time, source}
    """
    if image_name.startswith("-"):
        return {
            "image": image_name,
            "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
            "vulnerabilities": [],
            "source": "validation",
            "error": "Invalid container image name.",
        }

    if _trivy_available():
        try:
            cmd = [
                _trivy_path(), "image",
                "--format", "json",
                "--quiet",
                "--",
                image_name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return _parse_trivy_output(image_name, data)
            logger.warning("[Trivy] scan failed: %s", result.stderr[:200])
            return {
                "image": image_name,
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "vulnerabilities": [],
                "source": "trivy-cli",
                "error": (result.stderr or "Trivy image scan failed.")[:300],
            }
        except subprocess.TimeoutExpired:
            logger.error("[Trivy] scan timed out for %s", image_name)
            return {
                "image": image_name,
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "vulnerabilities": [],
                "source": "trivy-cli",
                "error": "Trivy image scan timed out.",
            }
        except Exception as exc:
            logger.error("[Trivy] error: %s", exc)
            return {
                "image": image_name,
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "vulnerabilities": [],
                "source": "trivy-cli",
                "error": "Trivy image scan failed unexpectedly.",
            }

    return _mock_scan(image_name)


def scan_filesystem(path: str = ".") -> dict:
    """Scan the filesystem for vulnerabilities in dependencies."""
    if path.startswith("-"):
        return {
            "image": f"filesystem:{path}",
            "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
            "vulnerabilities": [],
            "source": "validation",
            "error": "Invalid filesystem path.",
        }
    if _trivy_available():
        try:
            cmd = [_trivy_path(), "fs", "--format", "json", "--quiet", "--", path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return _parse_trivy_output(f"filesystem:{path}", data)
            return {
                "image": f"filesystem:{path}",
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "vulnerabilities": [],
                "source": "trivy-cli",
                "error": (result.stderr or "Trivy filesystem scan failed.")[:300],
            }
        except Exception as exc:
            logger.error("[Trivy] filesystem scan error: %s", exc)
            return {
                "image": f"filesystem:{path}",
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "vulnerabilities": [],
                "source": "trivy-cli",
                "error": "Trivy filesystem scan failed unexpectedly.",
            }
    return _mock_scan(f"filesystem:{path}")


def _parse_trivy_output(target: str, data: dict) -> dict:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    vulns = []
    for result in data.get("Results", []):
        for v in result.get("Vulnerabilities") or []:
            sev = v.get("Severity", "UNKNOWN").upper()
            counts[sev] = counts.get(sev, 0) + 1
            vulns.append({
                "id":          v.get("VulnerabilityID"),
                "package":     v.get("PkgName"),
                "version":     v.get("InstalledVersion"),
                "fixed_in":    v.get("FixedVersion", "No fix available"),
                "severity":    sev,
                "title":       v.get("Title", ""),
                "description": (v.get("Description") or "")[:200],
            })
    return {
        "image":           target,
        "critical":        counts["CRITICAL"],
        "high":            counts["HIGH"],
        "medium":          counts["MEDIUM"],
        "low":             counts["LOW"],
        "total":           sum(counts.values()),
        "vulnerabilities": vulns[:50],   # cap at 50 for display
        "scan_time":       datetime.utcnow().isoformat(),
        "source":          "trivy",
    }


def _mock_scan(image_name: str) -> dict:
    import random
    critical = random.randint(0, 3)
    high     = random.randint(2, 8)
    medium   = random.randint(5, 15)
    low      = random.randint(3, 12)
    return {
        "image":    image_name,
        "critical": critical,
        "high":     high,
        "medium":   medium,
        "low":      low,
        "total":    critical + high + medium + low,
        "vulnerabilities": [
            {"id": "CVE-2024-1234", "package": "openssl", "version": "3.0.11", "fixed_in": "3.0.12",
             "severity": "HIGH",     "title": "Buffer overflow in TLS handshake", "description": "Mock vulnerability"},
            {"id": "CVE-2024-5678", "package": "python",  "version": "3.11.5",  "fixed_in": "3.11.7",
             "severity": "MEDIUM",   "title": "Regular expression DoS",          "description": "Mock vulnerability"},
            {"id": "CVE-2023-9012", "package": "curl",    "version": "8.1.2",   "fixed_in": "8.4.0",
             "severity": "CRITICAL", "title": "HTTP/2 rapid reset vulnerability","description": "Mock vulnerability"},
        ],
        "scan_time": datetime.utcnow().isoformat(),
        "source":    "mock (trivy not installed)",
    }
