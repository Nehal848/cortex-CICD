"""
Root Cause Analysis Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Rule-based + pattern-matching RCA for CI/CD failures.
Analyses failure type, console log snippets, and pod metrics
to produce human-readable explanations and recommendations.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Failure pattern library ────────────────────────────────────────

_PATTERNS = [
    {
        "id": "oom_kill",
        "failure_types": ["OOM", "OOM — Pod Evicted", "Out of Memory"],
        "log_patterns": [r"OOMKilled", r"Killed", r"memory limit", r"cannot allocate memory"],
        "root_cause": "Container exceeded its memory limit and was OOM-killed by the kernel.",
        "evidence_template": "Container reached memory limit. Pod status shows OOMKilled.",
        "recommendations": [
            "Increase memory limit in Kubernetes deployment YAML",
            "Profile application for memory leaks",
            "Enable memory request/limit autoscaling (VPA)",
            "Add memory profiling to CI test stage",
        ],
        "confidence_base": 0.92,
    },
    {
        "id": "crash_loop",
        "failure_types": ["CrashLoopBackOff", "Liveness Probe Fail"],
        "log_patterns": [r"CrashLoopBackOff", r"liveness probe failed", r"Back-off restarting", r"exit code 1", r"connection refused"],
        "root_cause": "Container is crashing repeatedly. Likely cause: misconfigured port, missing env var, or startup error.",
        "evidence_template": "Pod restarted {restarts} times. Liveness probe failing.",
        "recommendations": [
            "Check EXPOSE port in Dockerfile matches Kubernetes liveness probe port",
            "Verify all required environment variables are set in the deployment",
            "Review container startup logs for the first error before crash",
            "Add a startup probe with an initialDelaySeconds buffer",
        ],
        "confidence_base": 0.88,
    },
    {
        "id": "network_timeout",
        "failure_types": ["Network Timeout", "Timeout", "Test Suite Timeout"],
        "log_patterns": [r"timeout", r"connection timed out", r"deadline exceeded", r"ETIMEDOUT", r"Read timed out"],
        "root_cause": "Network call or external dependency did not respond within the timeout window.",
        "evidence_template": "Timeout detected in build log. Possible external service degradation.",
        "recommendations": [
            "Increase timeout thresholds for external API calls",
            "Add circuit breaker pattern for external dependencies",
            "Check network egress rules and DNS resolution in the cluster",
            "Add retry logic with exponential backoff",
        ],
        "confidence_base": 0.85,
    },
    {
        "id": "dependency_error",
        "failure_types": ["Dependency Resolution", "Build Script Error"],
        "log_patterns": [r"could not resolve", r"package not found", r"npm ERR", r"pip install.*error",
                         r"ModuleNotFoundError", r"ImportError", r"No matching distribution"],
        "root_cause": "Build failed due to a missing or incompatible dependency.",
        "evidence_template": "Dependency resolution error in build log.",
        "recommendations": [
            "Pin all dependency versions in requirements.txt / package.json",
            "Use a private package mirror to avoid upstream outages",
            "Cache dependencies in the CI pipeline to reduce resolution failures",
            "Run dependency audit in the pre-build stage",
        ],
        "confidence_base": 0.90,
    },
    {
        "id": "high_cpu",
        "failure_types": ["High CPU Saturation"],
        "log_patterns": [r"CPU throttling", r"cpu limit", r"high cpu", r"load average"],
        "root_cause": "Pod CPU limit was hit, causing throttling and slow responses.",
        "evidence_template": "CPU throttling detected. Pod operating near its CPU limit.",
        "recommendations": [
            "Increase CPU limit in the deployment YAML",
            "Enable Horizontal Pod Autoscaler (HPA) based on CPU metrics",
            "Profile application for CPU-intensive hot paths",
            "Consider moving batch jobs to off-peak hours",
        ],
        "confidence_base": 0.87,
    },
    {
        "id": "probe_failure",
        "failure_types": ["Readiness Probe Fail", "Liveness Probe Fail"],
        "log_patterns": [r"readiness probe failed", r"liveness probe failed", r"probe.*failed", r"GET.*: dial tcp"],
        "root_cause": "Kubernetes probe could not reach the application health endpoint.",
        "evidence_template": "Health probe returned non-200 or timed out.",
        "recommendations": [
            "Verify /health or /ready endpoint is implemented and returns HTTP 200",
            "Check that the probe port and path match the application configuration",
            "Increase probe initialDelaySeconds if app has a slow startup",
            "Check service mesh (Istio/Linkerd) mTLS config is not blocking probe traffic",
        ],
        "confidence_base": 0.91,
    },
    {
        "id": "rollback_needed",
        "failure_types": ["Deploy Failure", "Image Pull Error"],
        "log_patterns": [r"ImagePullBackOff", r"ErrImagePull", r"image not found", r"manifest unknown"],
        "root_cause": "Kubernetes could not pull the container image. Image tag may not exist in the registry.",
        "evidence_template": "ImagePullBackOff: registry returned 404 or authentication error.",
        "recommendations": [
            "Verify the Docker image tag exists in the container registry",
            "Check imagePullSecrets are configured correctly in the namespace",
            "Roll back deployment to the last known-good image tag",
            "Check registry rate limits (Docker Hub: 100 pulls/6h for anonymous)",
        ],
        "confidence_base": 0.94,
    },
]

_DEFAULT_ANALYSIS = {
    "failure_type": "Unknown Failure",
    "root_cause": "Unable to determine a specific root cause. Manual investigation required.",
    "evidence": ["No matching failure pattern found in log analysis."],
    "confidence": 0.40,
    "recommendations": [
        "Review full console log for the first error message",
        "Check system resource usage (CPU, memory, disk) at time of failure",
        "Compare with the last successful build to identify changes",
        "Escalate to the on-call engineer if repeated failures occur",
    ],
    "pattern_id": "unknown",
}


# ── Public API ─────────────────────────────────────────────────────

def analyze(
    failure_type: str,
    console_log: str = "",
    pod_restarts: int = 0,
    risk_score: int = 0,
) -> dict:
    """
    Analyse a CI/CD failure and return a structured root cause report.

    Parameters
    ----------
    failure_type : str
        The failure category (e.g., "OOM", "CrashLoopBackOff").
    console_log  : str
        Raw console/build log text for pattern matching.
    pod_restarts : int
        Number of pod restarts (used as a severity signal).
    risk_score   : int
        ML-predicted risk score 0-100.

    Returns
    -------
    dict
        {failure_type, root_cause, evidence, confidence, recommendations, pattern_id}
    """
    log_lower = console_log.lower()
    best_match = None
    best_score = 0

    for pattern in _PATTERNS:
        score = 0

        # Type match
        for ft in pattern["failure_types"]:
            if ft.lower() in failure_type.lower() or failure_type.lower() in ft.lower():
                score += 5
                break

        # Log pattern match
        for regex in pattern["log_patterns"]:
            if re.search(regex, console_log, re.IGNORECASE):
                score += 2

        if score > best_score:
            best_score = score
            best_match = pattern

    if best_match is None or best_score < 2:
        result = dict(_DEFAULT_ANALYSIS)
        result["failure_type"] = failure_type or "Unknown Failure"
        return result

    evidence = [best_match["evidence_template"].format(restarts=pod_restarts)]
    # Add log excerpts as evidence
    for regex in best_match["log_patterns"]:
        m = re.search(regex, console_log, re.IGNORECASE)
        if m:
            # Extract surrounding context (up to 80 chars)
            start = max(0, m.start() - 20)
            end = min(len(console_log), m.end() + 40)
            snippet = console_log[start:end].strip().replace("\n", " ")
            evidence.append(f'Log: "…{snippet}…"')
            if len(evidence) >= 3:
                break

    # Adjust confidence based on evidence strength
    confidence = best_match["confidence_base"]
    if best_score >= 7:
        confidence = min(0.99, confidence + 0.04)
    elif best_score <= 3:
        confidence = max(0.50, confidence - 0.15)

    return {
        "failure_type": failure_type,
        "root_cause": best_match["root_cause"],
        "evidence": evidence,
        "confidence": round(confidence, 2),
        "recommendations": best_match["recommendations"],
        "pattern_id": best_match["id"],
    }


def analyze_risk_factors(run: dict) -> list[str]:
    """Return human-readable risk factors for a pipeline run."""
    factors = []
    if run.get("risk_score", 0) >= 75:
        factors.append("High ML-predicted risk score")
    branch = run.get("branch", "")
    if branch and "main" not in branch and "master" not in branch:
        factors.append(f"Non-main branch: {branch}")
    duration = run.get("duration_secs", 0)
    if duration and duration > 250:
        factors.append(f"Unusually long build duration ({duration}s)")
    elif duration and duration < 30:
        factors.append(f"Suspiciously fast build ({duration}s) — may have skipped stages")
    triggered = run.get("triggered_by", "")
    if triggered == "Manual":
        factors.append("Manually triggered (not from Git)")
    return factors if factors else ["No significant risk factors detected"]
