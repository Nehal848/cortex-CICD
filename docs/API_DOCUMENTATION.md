# CortexCICD — Complete REST API Documentation

This document provides a technical reference for CortexCICD's REST API, webhooks, health probes, observability metrics, and authentication endpoints. All `/api/*` endpoints accept **either** an authenticated Flask session cookie **or** a programmatic `Authorization: Bearer <token>` / `X-API-Key: <token>` header.

---

## 1. Authentication & Platform Settings Endpoints

| Method | Endpoint | Purpose | Auth Required | Parameters / Body | Response Format |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/login` | Render login form | No | None | `text/html` |
| `POST` | `/login` | Authenticate user session (rate-limited, DB hashed password + env fallback) | No | Form data: `username`, `password`, `csrf_token` | Redirect (`302`) to `/dashboard` or `401`/`429` error |
| `POST` | `/logout` | Terminate session (CSRF-protected) | Yes | Form/Header: `csrf_token` / `X-CSRF-Token` | Redirect (`302`) to `/login` |
| `POST` | `/api/auth/token` | Generate a scoped Bearer / `X-API-Key` token (SHA-256 hashed, optional expiry) | Yes | Optional JSON: `{"expires_days": 90}` | `{"token": "cx_...", "username": "...", "expires_at": "...", "header_example": "..."}` |
| `DELETE` | `/api/auth/token` | Revoke the current user's API token immediately | Yes | None | `{"status": "revoked", "username": "..."}` |
| `GET` | `/api/settings` | Read persisted platform settings | Yes | None | `{"settings": {"cpu_threshold": "85", ...}}` |
| `POST` | `/api/settings` | Persist platform settings & thresholds to DB | Yes | JSON settings dict (`cpu_threshold`, `slack_notifications`, etc.) | `{"status": "saved", "updated": [...], "settings": {...}}` |

---

## 2. CI/CD Pipeline & Execution Endpoints

### `POST /api/pipeline/run`
- **Purpose:** Trigger a new pipeline execution, calculate initial ML risk score, and initiate background status polling.
- **Service:** `app/services/pipeline_service.py` (`trigger_pipeline`)
- **Validation:** `validate_pipeline_run` in `app/validation.py`
- **Request Headers:** `Content-Type: application/json`
- **Request Body:**
  ```json
  {
    "repo": "CortexCICD/Self-Healing-CI-CD",
    "branch": "main",
    "triggered_by": "GitPush",
    "job_name": "CortexCICD/Self-Healing-CI-CD"
  }
  ```
- **Response (`201 Created`):**
  ```json
  {
    "run_id": "RUN-4820",
    "repo": "CortexCICD/Self-Healing-CI-CD",
    "branch": "main",
    "status": "In Progress",
    "triggered_by": "GitPush",
    "risk_score": 14,
    "jenkins_job_name": "CortexCICD/Self-Healing-CI-CD",
    "jenkins_build_number": 143,
    "created_at": "2026-11-10T14:30:00.000000"
  }
  ```

---

## 3. AI Prediction & Root Cause Analysis Endpoints

### `GET /api/predict/<run_id>`
- **Purpose:** Generate failure probability, predicted failure category, risk score (0-100), and recommended recovery strategy.
- **Service:** `app/services/prediction_service.py` (`get_prediction_for_run`)
- **Response (`200 OK`):**
  ```json
  {
    "run_id": "RUN-4816",
    "risk_score": 28,
    "risk_level": "Low",
    "failure_type": "None",
    "confidence": 1.0,
    "confidence_label": "Very High",
    "recommended_action": "No action required",
    "preventative_action": "Monitor metrics",
    "consecutive_failures": 0,
    "model": "RandomForestClassifier (n=2000, 100 trees)"
  }
  ```

### `POST /api/analyze`
- **Purpose:** Execute pattern-matching Root Cause Analysis (RCA) on failure types, console log snippets, and pod restart counters.
- **Service:** `ml/root_cause.py` (`analyze`)
- **Request Body:**
  ```json
  {
    "failure_type": "OOM — Pod Evicted",
    "log_snippet": "OOMKilled: container exceeded memory limit 512Mi",
    "run_id": "RUN-4814",
    "pod_restarts": 1,
    "risk_score": 65
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "run_id": "RUN-4814",
    "pattern_id": "oom_kill",
    "root_cause": "Container exceeded its memory limit and was OOM-killed by the kernel.",
    "confidence": 0.92,
    "confidence_label": "Very High",
    "evidence": [
      "Container reached memory limit. Pod status shows OOMKilled.",
      "Log matched: OOMKilled"
    ],
    "recommendations": [
      "Increase memory limit in Kubernetes deployment YAML",
      "Profile application for memory leaks",
      "Enable memory request/limit autoscaling (VPA)",
      "Add memory profiling to CI test stage"
    ],
    "risk_factors": [
      "High failure risk score (65/100)"
    ]
  }
  ```

### `POST /api/ml/retrain`
- **Purpose:** Retrain failure risk regressor and classifier from real historical database records.
- **Service:** `ml/predict_failure.py` (`retrain_from_database`)
- **Request Body:** `{"min_samples": 5}`
- **Response (`200 OK`):**
  ```json
  {
    "retrained": true,
    "samples_used": 14,
    "model_path": "ml/models/failure_predictor.pkl",
    "status": "Models successfully retrained from database telemetry."
  }
  ```

---

## 4. Autonomous Self-Healing Endpoints

### `POST /api/heal/<run_id>`
- **Purpose:** Manually trigger the self-healing cycle for a pipeline run.
- **Service:** `app/healing/engine.py` (`HealingEngine.handle_failure`)
- **Optional Request Body:**
  ```json
  {
    "failure_type": "OOM — Pod Evicted",
    "pod_name": "cortex-api-pod",
    "deployment_name": "cortex-api",
    "namespace": "default"
  }
  ```
- **Response (`200 OK`):**
  ```json
  {
    "run_id": "RUN-4814",
    "failure_type": "OOM — Pod Evicted",
    "strategy": "Pod Restart",
    "outcome": "Resolved",
    "success": true,
    "message": "Pod cortex-api-pod deleted successfully.",
    "actions_taken": [
      "Identified failing pod: cortex-api-pod in namespace default",
      "Initiated pod deletion via Kubernetes API",
      "Pod successfully terminated; replica recreation in progress"
    ],
    "duration_ms": 420,
    "timestamp": "2026-11-10T14:32:00.000000"
  }
  ```

### `GET /api/healing/status`
- **Purpose:** Retrieve active status of the healing engine and recent healing history.
- **Response (`200 OK`):**
  ```json
  {
    "status": "Active",
    "auto_heal_enabled": true,
    "active_heals": 0,
    "recent_events": [
      {
        "run_id": "RUN-4818",
        "failure_type": "Test Suite Timeout",
        "strategy": "Auto Retry",
        "outcome": "Resolved",
        "timestamp": "10 mins ago"
      }
    ]
  }
  ```

---

## 5. Alert Lifecycle Management Endpoints

| Method | Endpoint | Validation Function | Expected Body / Query | Success Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/alerts/active` | None | None | List of alerts where status in `('Active', 'Acknowledged')` |
| `GET` | `/api/alerts/history` | None | Query: `?page=1&per_page=20` | Paginated resolved and archived alert history |
| `POST` | `/api/alerts/<id>/acknowledge` | None | None | `{"message": "Alert acknowledged", "status": "Acknowledged"}` |
| `POST` | `/api/alerts/<id>/resolve` | None | None | `{"message": "Alert resolved", "status": "Resolved"}` |
| `POST` | `/api/alerts/<id>/silence` | `validate_silence_duration` | `{"duration_hours": 4}` | `{"message": "Alert silenced", "silenced_until": "..."}` |
| `POST` | `/api/alerts/<id>/archive` | None | None | `{"message": "Alert archived", "status": "Archived"}` |

---

## 6. Real-Time Telemetry & SSE Stream

### `GET /api/stream`
- **Purpose:** Server-Sent Events (SSE) pipe delivering real-time pipeline, alert, and healing notifications.
- **Service:** `app/events.py` (`subscribe`)
- **Headers Returned:**
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
- **Sample Stream Output:**
  ```text
  event: pipeline.updated
  data: {"run_id": "RUN-4820", "status": "Success", "duration_secs": 115}

  event: healing.started
  data: {"run_id": "RUN-4816", "failure_type": "Dependency Resolution"}

  : ping
  ```

---

## 7. Infrastructure Integration Endpoints (Docker, K8s, Jenkins, Prometheus)

| Method | Endpoint | Integration Client | Real / Fallback Behavior |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/docker/containers` | `docker_client.py` | Queries local Docker daemon; falls back to 5 simulated containers. |
| `POST` | `/api/docker/restart/<id>`| `docker_client.py` | Restarts container via Docker SDK; returns mock success if daemon unreachable. |
| `DELETE`| `/api/docker/remove/<id>` | `docker_client.py` | Removes container via Docker SDK; returns mock success if unreachable. |
| `GET` | `/api/docker/stats/<id>` | `docker_client.py` | Returns CPU% and memory MB; returns simulated randomized metrics on fallback. |
| `GET` | `/api/k8s/pods` | `k8s_client.py` | Queries CoreV1Api `list_namespaced_pod`; falls back to 6 mock pods. |
| `GET` | `/api/k8s/deployments` | `k8s_client.py` | Queries AppsV1Api; falls back to 4 mock deployments. |
| `GET` | `/api/k8s/nodes` | `k8s_client.py` | Queries node statuses; falls back to 3 mock worker nodes. |
| `GET` | `/api/k8s/services` | `k8s_client.py` | Queries Kubernetes Services; falls back to 4 mock services. |
| `POST` | `/api/k8s/restart/<pod>` | `k8s_client.py` | Deletes pod to trigger ReplicaSet recreation. |
| `POST` | `/api/k8s/scale/<deploy>`| `k8s_client.py` | Scaled deployment replicas (`{"replicas": 3}`). |
| `GET` | `/api/jenkins/jobs` | `jenkins_client.py` | Queries python-jenkins REST server; falls back to 3 mock jobs. |
| `POST` | `/api/jenkins/trigger/<job>`| `jenkins_client.py`| Invokes `build_job` on Jenkins; returns mock build number on fallback. |
| `GET` | `/api/jenkins/log/<job>/<num>`| `jenkins_client.py`| Fetches console output for build; falls back to mock test log. |
| `GET` | `/api/prometheus/metrics`| `prometheus_client.py`| Fetches memory, CPU, cluster health metrics from Prometheus. |
| `GET` | `/api/prometheus/http_rate`| `prometheus_client.py`| Fetches HTTP request rates per second. |

---

## 8. DevSecOps Security Endpoints

### `POST /api/security/scan`
- **Purpose:** Trigger vulnerability scan for a container image.
- **Service:** `app/security/scanner.py` (`scan_image`)
- **Request Body:** `{"image_name": "cortex-api:v2.4.1"}`
- **Response (`200 OK`):**
  ```json
  {
    "image": "cortex-api:v2.4.1",
    "critical": 0,
    "high": 2,
    "medium": 5,
    "low": 12,
    "total": 19,
    "source": "trivy-cli (or mock-fallback)",
    "scan_time": "2026-11-10T14:35:00.000000",
    "vulnerabilities": [
      {
        "cve_id": "CVE-2026-1402",
        "severity": "HIGH",
        "package": "cryptography",
        "installed_version": "41.0.2",
        "fixed_version": "42.0.0",
        "description": "Buffer overflow vulnerability in cryptographic parser."
      }
    ]
  }
  ```

### `GET /api/security/secrets`
- **Purpose:** Scan repository filesystem for plaintext secrets, API keys, and RSA private keys.
- **Service:** `app/security/secret_scanner.py` (`scan_secrets`)
- **Response (`200 OK`):** Returns list of detected secret patterns with filename and line numbers.

### `POST /api/security/sbom`
- **Purpose:** Generate a Software Bill of Materials (SBOM) for a container image via Syft.
- **Service:** `app/security/sbom.py` (`generate_sbom`)
- **Request Body:** `{"image": "cortex-api:v2.4.1", "format": "spdx-json"}`
- **Response (`200 OK`):** Returns standardized SPDX/CycloneDX JSON package manifest.

### `POST /api/security/cosign/verify`
- **Purpose:** Cryptographically verify container image signatures using Sigstore Cosign.
- **Service:** `app/security/cosign.py` (`verify_image_signature`)
- **Request Body:** `{"image": "cortex-api:v2.4.1", "public_key": "optional-path-or-url"}`
- **Response (`200 OK`):** Returns verification status, signer claims, and certificate issuer metadata.

---

## 9. Trusted Execution Environment (TEE) Endpoints

| Method | Endpoint | Service | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/tee/status` | `app/tee/enclave.py` | Checks simulated enclave initialization, MRENCLAVE measurement, and sealing status. |
| `GET` | `/api/tee/attestation` | `app/tee/attestation.py` | Generates simulated Intel SGX Remote Attestation quote with IAS signature and security score. |
| `GET` | `/api/tee/secrets` | `app/tee/secrets.py` | Lists names of sealed secrets stored in encrypted storage. |
| `POST` | `/api/tee/seal` | `app/tee/secrets.py` | Encrypts and seals a secret (`{"key": "DB_PASS", "value": "secret"}`) using AES-256-GCM enclave key. |

---

## 10. Report Export Endpoints

- **`GET /api/reports/pipeline`**: Downloads `pipeline_report.pdf` (or JSON fallback) containing run history and cluster success rate.
- **`GET /api/reports/healing`**: Downloads `healing_report.pdf` (or JSON fallback) containing autonomous healing audit log.
- **`GET /api/reports/ai/<run_id>`**: Downloads `ai_report_<run_id>.pdf` containing risk breakdown, failure diagnosis, and recommendations.

---

## 11. Inbound Webhooks

- **`POST /webhooks/github`**: Handles `push`, `pull_request`, and `ping` GitHub events. Validates HMAC-SHA256 signature (`X-Hub-Signature-256`; fails closed in production/strict mode). Automatically creates pipeline run on push.
- **`POST /webhooks/jenkins`**: Ingests build notifications (`SUCCESS`, `FAILURE`). Validates `JENKINS_WEBHOOK_SECRET` (`Authorization: Bearer` or `X-Jenkins-Token`; fails closed in production/strict mode) and triggers `HealingEngine` on failure.
- **`POST /webhooks/prometheus`**: Ingests Alertmanager webhook alerts. Validates `ALERTMANAGER_TOKEN` (`Authorization: Bearer` or `X-Alertmanager-Token`; fails closed in production/strict mode), creates new `Alert` records for `firing` alerts, and resolves alerts for `resolved` status.

---

## 12. Health Check & Observability Probes

- **`GET /healthz`**: Kubernetes liveness probe. Always returns HTTP 200 `{"status": "ok"}`.
- **`GET /readyz`**: Kubernetes readiness probe. Queries database `SELECT 1` and validates ML model cache. Returns HTTP 200 or 503.
- **`GET /livez`**: Comprehensive component health check returning uptime and subsystem states.
- **`GET /metrics`**: Prometheus exposition endpoint serving `flask_http_request_total`, `flask_http_request_duration_seconds`, `cortex_pipeline_runs_total`, `cortex_healing_events_total`, and `cortex_sse_subscribers`.

