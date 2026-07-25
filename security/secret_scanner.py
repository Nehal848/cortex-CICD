"""
Secret Scanner
~~~~~~~~~~~~~~
Scans the project codebase for accidentally committed secrets using regex patterns.
Identifies: API keys, tokens, passwords, private keys, connection strings.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Secret detection patterns
_PATTERNS = [
    {"name": "AWS Access Key",      "pattern": r"AKIA[0-9A-Z]{16}",                        "severity": "CRITICAL"},
    {"name": "AWS Secret Key",      "pattern": r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-z/+]{40}['\"]", "severity": "CRITICAL"},
    {"name": "Private Key Header",  "pattern": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "severity": "CRITICAL"},
    {"name": "GitHub Token",        "pattern": r"ghp_[a-zA-Z0-9]{36}",                     "severity": "HIGH"},
    {"name": "Generic API Key",     "pattern": r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?[a-z0-9]{20,}['\"]?", "severity": "HIGH"},
    {"name": "Generic Password",    "pattern": r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{6,}['\"]", "severity": "HIGH"},
    {"name": "Generic Secret",      "pattern": r"(?i)(secret[_-]?key|client_secret)\s*[=:]\s*['\"][^'\"]{8,}['\"]", "severity": "HIGH"},
    {"name": "Slack Webhook",       "pattern": r"https://hooks.slack.com/services/[A-Z0-9/]+",  "severity": "MEDIUM"},
    {"name": "Connection String",   "pattern": r"(?i)(mongodb|postgresql|mysql|redis)://[^\s\"']+:[^\s\"'@]+@", "severity": "HIGH"},
    {"name": "JWT Token",           "pattern": r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", "severity": "MEDIUM"},
    {"name": "Basic Auth in URL",   "pattern": r"https?://[a-zA-Z0-9_-]+:[a-zA-Z0-9_!@#$%^&*-]+@", "severity": "HIGH"},
    {"name": "Google API Key",      "pattern": r"AIza[0-9A-Za-z\-_]{35}",                  "severity": "HIGH"},
]

# Files and directories to skip
_SKIP_DIRS  = {".git", "venv", "__pycache__", ".pytest_cache", "node_modules",
               ".env", "tee", "ml/models", ".gemini", ".augment"}
_SKIP_EXTS  = {".pyc", ".pyo", ".pkl", ".enc", ".png", ".jpg", ".jpeg",
               ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map"}
_SKIP_FILES = {".env"}  # .env intentionally contains credentials


def scan_directory(root_path: str = ".") -> dict:
    """
    Scan a directory tree for secret patterns.

    Returns
    -------
    dict
        {total_files, findings, summary_by_severity, scan_time}
    """
    root = Path(root_path).resolve()
    findings = []
    total_files = 0

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue
        if path.suffix.lower() in _SKIP_EXTS:
            continue
        if path.name in _SKIP_FILES:
            continue
        if path.stat().st_size > 500_000:  # skip files > 500 KB
            continue

        total_files += 1
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pat in _PATTERNS:
            matches = list(re.finditer(pat["pattern"], content))
            for m in matches:
                # Find line number
                line_num = content[:m.start()].count("\n") + 1
                # Redact value for display
                matched = m.group()
                redacted = matched[:6] + "…" + matched[-4:] if len(matched) > 12 else "***"
                findings.append({
                    "file":     str(path.relative_to(root)),
                    "line":     line_num,
                    "type":     pat["name"],
                    "severity": pat["severity"],
                    "match":    redacted,
                })

    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1

    return {
        "total_files":          total_files,
        "total_findings":       len(findings),
        "findings":             findings,
        "summary_by_severity":  summary,
        "scan_time":            datetime.utcnow().isoformat(),
        "source":               "cortex-secret-scanner",
    }
