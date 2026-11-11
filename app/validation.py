"""
Input Validation
~~~~~~~~~~~~~~~~
Lightweight, zero-dependency validation for all mutable API endpoints.

Every public function returns:
    (cleaned_data: dict, errors: list[str])

If errors is non-empty, callers should return HTTP 400:

    data, errors = validate_pipeline_run(request.json or {})
    if errors:
        return jsonify({"errors": errors}), 400

No third-party schema library is required — pure stdlib re + builtins.
"""

import re

# ── Allowed value sets ─────────────────────────────────────────────

VALID_TRIGGERED_BY = {
    "GitPush", "Manual", "Scheduled", "PullRequest", "PrometheusAlert"
}
VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}
VALID_ENVIRONMENTS = {"Production", "Staging", "Dev"}
VALID_JENKINS_RESULTS = {"SUCCESS", "FAILURE", "ABORTED", "UNSTABLE"}
VALID_ALERT_STATUSES = {
    "Active", "Acknowledged", "Silenced", "Resolved", "Archived"
}
VALID_SBOM_FORMATS = {"spdx-json", "cyclonedx-json", "syft-json"}

# ── Compiled patterns ──────────────────────────────────────────────

_REPO_RE      = re.compile(r'^[\w\-./]{1,120}$')
_BRANCH_RE    = re.compile(r'^[\w\-./]{1,80}$')
_DEP_NAME_RE  = re.compile(r'^[\w\-]{1,80}$')
_IMAGE_RE     = re.compile(r'^[a-zA-Z0-9][\w\-./:@]{0,199}$')
_NAMESPACE_RE = re.compile(r'^[\w\-]{1,63}$')
_RUN_ID_RE    = re.compile(r'^[\w\-]{1,40}$')
_K8S_ID_RE    = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-_.]{0,62}$')


# ── Primitive validators ───────────────────────────────────────────

def _str(value, field: str, max_len: int = 120,
         required: bool = True) -> tuple[str, str | None]:
    """Coerce to stripped string and validate presence + length."""
    if value is None:
        if required:
            return "", f"'{field}' is required"
        return "", None
    s = str(value).strip()
    if not s and required:
        return "", f"'{field}' must not be empty"
    if len(s) > max_len:
        return s[:max_len], f"'{field}' must be ≤{max_len} characters"
    return s, None


def _int_range(value, field: str, lo: int, hi: int,
               required: bool = True) -> tuple[int, str | None]:
    """Validate integer within [lo, hi]."""
    if value is None:
        if required:
            return 0, f"'{field}' is required"
        return 0, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0, f"'{field}' must be an integer"
    if not lo <= n <= hi:
        return n, f"'{field}' must be between {lo} and {hi} (got {n})"
    return n, None


def _enum(value, field: str, choices: set,
          required: bool = True) -> tuple[str, str | None]:
    """Validate string membership in a set of allowed values."""
    if value is None:
        if required:
            return "", f"'{field}' is required"
        return "", None
    s = str(value).strip()
    if s not in choices:
        return s, f"'{field}' must be one of {sorted(choices)} (got '{s}')"
    return s, None


# ── Public validators ──────────────────────────────────────────────

def validate_pipeline_run(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /api/pipeline/run body."""
    errors: list[str] = []

    job_name, e = _str(data.get("job_name"), "job_name")
    if e:
        errors.append(e)
    elif not _REPO_RE.match(job_name):
        errors.append("'job_name' contains invalid characters (allowed: a-z A-Z 0-9 - _ . /)")

    branch, e = _str(data.get("branch"), "branch")
    if e:
        errors.append(e)
    elif not _BRANCH_RE.match(branch):
        errors.append("'branch' contains invalid characters (allowed: a-z A-Z 0-9 - _ . /)")

    return {"job_name": job_name, "branch": branch}, errors


def validate_alert_silence(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /api/alerts/<id>/silence body."""
    errors: list[str] = []

    duration, e = _int_range(
        data.get("duration_minutes"), "duration_minutes",
        lo=1, hi=10_080,   # 1 minute … 1 week
    )
    if e:
        errors.append(e)

    return {"duration_minutes": duration}, errors


def validate_security_scan(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /api/security/scan body."""
    errors: list[str] = []

    image, e = _str(
        data.get("image", "cortex-api:latest"), "image",
        max_len=200, required=False,
    )
    if e:
        errors.append(e)
    elif image and not _IMAGE_RE.match(image):
        errors.append("'image' contains invalid characters")

    return {"image": image or "cortex-api:latest"}, errors


def validate_k8s_scale(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /api/k8s/scale/<deployment> body."""
    errors: list[str] = []

    replicas, e = _int_range(data.get("replicas"), "replicas", lo=1, hi=10)
    if e:
        errors.append(e)

    namespace, e = _str(
        data.get("namespace", "default"), "namespace",
        max_len=63, required=False,
    )
    if e:
        errors.append(e)
    elif namespace and not _NAMESPACE_RE.match(namespace):
        errors.append("'namespace' contains invalid characters (DNS label format required)")

    return {"replicas": replicas, "namespace": namespace or "default"}, errors


def validate_analyze(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /api/analyze body."""
    errors: list[str] = []

    failure_type, e = _str(
        data.get("failure_type", ""), "failure_type",
        max_len=80, required=False,
    )
    if e:
        errors.append(e)

    risk_score, e = _int_range(
        data.get("risk_score", 0), "risk_score", lo=0, hi=100, required=False
    )
    if e:
        errors.append(e)

    pod_restarts, e = _int_range(
        data.get("pod_restarts", 0), "pod_restarts", lo=0, hi=9_999, required=False
    )
    if e:
        errors.append(e)

    log_snippet = str(data.get("log_snippet", ""))[:5_000]
    run_id      = str(data.get("run_id", ""))[:40]

    return {
        "failure_type": failure_type,
        "log_snippet":  log_snippet,
        "run_id":       run_id,
        "pod_restarts": pod_restarts,
        "risk_score":   risk_score,
    }, errors


def validate_webhook_jenkins(data: dict) -> tuple[dict, list[str]]:
    """Validate POST /webhooks/jenkins body."""
    errors: list[str] = []

    run_id, e = _str(data.get("run_id"), "run_id", max_len=40)
    if e:
        errors.append(e)
    elif run_id and not _RUN_ID_RE.match(run_id):
        errors.append("'run_id' contains invalid characters")

    result = str(data.get("result", "UNKNOWN")).strip().upper()
    if result not in (VALID_JENKINS_RESULTS | {"UNKNOWN", "IN_PROGRESS", "NOT_BUILT"}):
        errors.append(
            f"'result' must be one of {sorted(VALID_JENKINS_RESULTS)} (got '{result}')"
        )

    duration_ms, e = _int_range(
        data.get("duration_ms", 0), "duration_ms",
        lo=0, hi=86_400_000, required=False,  # 0ms … 24h
    )
    if e:
        errors.append(e)

    build_number = data.get("build_number")
    if build_number is not None:
        try:
            build_number = int(build_number)
        except (TypeError, ValueError):
            errors.append("'build_number' must be an integer")
            build_number = None

    return {
        "run_id":       run_id,
        "result":       result,
        "duration_ms":  duration_ms,
        "build_number": build_number,
        "job_name":     str(data.get("job_name", ""))[:120],
        "console_log":  str(data.get("console_log", ""))[:5_000],
    }, errors


def validate_sbom_format(fmt: str | None) -> tuple[str, str | None]:
    """Validate Syft SBOM output format against strict allowlist."""
    val = (fmt or "spdx-json").strip()
    if val not in VALID_SBOM_FORMATS:
        return val, f"'format' must be one of {sorted(VALID_SBOM_FORMATS)}"
    return val, None


def validate_cosign_public_key(public_key: str | None) -> tuple[str | None, str | None]:
    """Reject CLI option flags, whitespace, or path traversal in Cosign public key."""
    if not public_key:
        return None, None
    key = str(public_key).strip()
    if not key:
        return None, None
    if key.startswith("-") or any(c.isspace() for c in key) or ".." in key:
        return None, "'public_key' contains disallowed characters or path traversal"
    if not (key.startswith("https://") or key.startswith("k8s://") or re.match(r'^[\w\-./]{1,200}$', key)):
        return None, "'public_key' must be an https:// URL, k8s:// ref, or relative key path"
    return key, None


def sanitize_k8s_identifier(value: str | None, default: str) -> str:
    """Return value if it is a safe Kubernetes identifier, otherwise default."""
    if not value:
        return default
    cleaned = str(value).strip()[:63]
    return cleaned if _K8S_ID_RE.match(cleaned) else default


def validate_service_url(url: str | None, field: str) -> tuple[str, str | None]:
    """Validate external integration URLs against SSRF / metadata endpoints."""
    import ipaddress
    from urllib.parse import urlparse

    raw = str(url or "").strip()
    if not raw or len(raw) > 250:
        return "", f"'{field}' must be a non-empty URL under 250 characters."

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "", f"'{field}' must be a valid http(s) URL."
    if parsed.username or parsed.password:
        return "", f"'{field}' must not embed credentials in URL."

    host = parsed.hostname.lower().rstrip(".")
    if host in ("metadata.google.internal", "metadata", "0.0.0.0"):
        return "", f"'{field}' points to a disallowed internal host."

    try:
        ip_obj = ipaddress.ip_address(host)
        if ip_obj.is_link_local or ip_obj.is_unspecified or ip_obj.is_multicast:
            return "", f"'{field}' points to a disallowed link-local or unspecified IP."
    except ValueError:
        pass  # DNS hostname — allowed (e.g. jenkins, prometheus, jenkins.company.internal)

    return raw.rstrip("/"), None
