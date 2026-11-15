"""Log-based feature extractor for ML pipeline."""
import re

LOG_PATTERNS = {
    "has_oom":          r"OOMKilled|cannot allocate memory|memory limit",
    "has_timeout":      r"timeout|ETIMEDOUT|deadline exceeded|timed out",
    "has_import_error": r"ModuleNotFoundError|ImportError|No module named",
    "has_test_fail":    r"FAILED|AssertionError|test.*failed|FAIL:",
    "has_network_err":  r"Connection refused|getaddrinfo failed|Name or service not known",
    "has_exit_code":    r"exit code [1-9]|exited with code [1-9]",
}


def extract_log_features(log_text: str) -> dict:
    """Return a dict of boolean (0/1) features extracted from a build log."""
    if not log_text:
        return {k: 0 for k in LOG_PATTERNS}
    return {k: int(bool(re.search(v, log_text, re.I))) for k, v in LOG_PATTERNS.items()}
