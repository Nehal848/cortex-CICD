"""
Syft Software Bill of Materials (SBOM) Generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Wraps the Syft CLI to generate standardized SBOMs (SPDX / CycloneDX).
Falls back to a structured mock SBOM if the syft CLI is not installed.
"""

import os
import json
import logging
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _syft_path() -> str:
    return os.getenv("SYFT_PATH", "syft")


def _syft_available() -> bool:
    try:
        result = subprocess.run(
            [_syft_path(), "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def generate_sbom(image_name: str = "cortex-api:latest", output_format: str = "spdx-json") -> dict:
    """
    Generate an SBOM for a container image.

    Parameters
    ----------
    image_name : str
        Target image name or filesystem path.
    output_format : str
        Format specifier: spdx-json | cyclonedx-json | syft-json

    Returns
    -------
    dict
        Parsed SBOM metadata, package count, packages list, and generation timestamp.
    """
    if image_name.startswith("-") or output_format not in {"spdx-json", "cyclonedx-json", "syft-json"}:
        return {
            "image": image_name,
            "format": output_format,
            "source": "validation",
            "total_packages": 0,
            "packages": [],
            "error": "Invalid image name or SBOM format.",
        }

    if _syft_available():
        try:
            cmd = [_syft_path(), image_name, "-o", output_format]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                raw_data = json.loads(result.stdout)
                return {
                    "image": image_name,
                    "format": output_format,
                    "source": "syft-cli",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_packages": len(raw_data.get("packages", raw_data.get("artifacts", []))),
                    "sbom": raw_data,
                }
            logger.warning("[Syft] CLI returned non-zero exit code: %s", result.stderr[:200])
            return {
                "image": image_name,
                "format": output_format,
                "source": "syft-cli",
                "total_packages": 0,
                "packages": [],
                "error": (result.stderr or "Syft SBOM generation failed.")[:300],
            }
        except subprocess.TimeoutExpired:
            logger.error("[Syft] CLI timed out analyzing image %s", image_name)
            return {
                "image": image_name,
                "format": output_format,
                "source": "syft-cli",
                "total_packages": 0,
                "packages": [],
                "error": "Syft execution timed out.",
            }
        except Exception as exc:
            logger.error("[Syft] Error executing Syft: %s", exc)
            return {
                "image": image_name,
                "format": output_format,
                "source": "syft-cli",
                "total_packages": 0,
                "packages": [],
                "error": "Syft execution failed unexpectedly.",
            }

    return _mock_sbom(image_name, output_format)


def _mock_sbom(image_name: str, output_format: str) -> dict:
    """Return a realistic SPDX-JSON formatted SBOM mock."""
    sample_packages = [
        {
            "name": "flask",
            "version": "3.1.2",
            "license": "BSD-3-Clause",
            "type": "python-package",
            "supplier": "Pallets Projects",
            "purl": "pkg:pypi/flask@3.1.2",
        },
        {
            "name": "cryptography",
            "version": "46.0.7",
            "license": "Apache-2.0 OR BSD-3-Clause",
            "type": "python-package",
            "supplier": "Python Cryptographic Authority",
            "purl": "pkg:pypi/cryptography@46.0.7",
        },
        {
            "name": "scikit-learn",
            "version": "1.9.0",
            "license": "BSD-3-Clause",
            "type": "python-package",
            "supplier": "Scikit-Learn Developers",
            "purl": "pkg:pypi/scikit-learn@1.9.0",
        },
        {
            "name": "reportlab",
            "version": "4.4.6",
            "license": "BSD-3-Clause",
            "type": "python-package",
            "supplier": "ReportLab Inc.",
            "purl": "pkg:pypi/reportlab@4.4.6",
        },
        {
            "name": "SQLAlchemy",
            "version": "2.0.51",
            "license": "MIT",
            "type": "python-package",
            "supplier": "SQLAlchemy Authors",
            "purl": "pkg:pypi/SQLAlchemy@2.0.51",
        },
        {
            "name": "alpine-baselayout",
            "version": "3.4.3-r3",
            "license": "GPL-2.0-only",
            "type": "apk",
            "supplier": "Alpine Linux",
            "purl": "pkg:alpine/alpine-baselayout@3.4.3-r3",
        },
    ]

    return {
        "image": image_name,
        "format": output_format,
        "source": "simulated-syft-fallback",
        "spdx_version": "SPDX-2.3",
        "data_license": "CC0-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_packages": len(sample_packages),
        "packages": sample_packages,
        "document_namespace": f"https://cortex.local/spdxdocs/{image_name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    }

