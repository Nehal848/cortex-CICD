# CortexCICD — Production Deployment & Operations Guide

## 1. Prerequisites & System Requirements

- **Operating System:** Linux (Ubuntu 22.04 LTS / RHEL 9 recommended), macOS, or Windows 10/11 with WSL2.
- **Runtime:** Python 3.10, 3.11, or 3.12.
- **Container Runtime:** Docker Engine 24.0+ and Docker Compose v2+.
- **Orchestration (Optional for Full Features):** Kubernetes 1.26+ (Minikube, Kind, k3s, EKS, GKE, or AKS).
- **CI Server (Optional for Real Builds):** Jenkins 2.400+ with Pipeline and Git plugins.

---

## 2. Local Development Deployment

### 1. Clone Repository & Initialize Virtual Environment
```bash
git clone https://github.com/CortexCICD/cortex-CICD.git
cd cortex-CICD

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a local `.env` file from the reference below:
```ini
FLASK_APP=app/app.py
FLASK_ENV=development
SECRET_KEY=change-this-to-a-secure-random-token
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password

# Optional Integrations (Defaults to realistic mock mode if omitted)
JENKINS_URL=http://localhost:8080
JENKINS_USER=admin
JENKINS_TOKEN=your-jenkins-api-token

K8S_KUBECONFIG=~/.kube/config
K8S_NAMESPACE=default

PROMETHEUS_URL=http://localhost:9090
GITHUB_WEBHOOK_SECRET=your-github-webhook-secret
```

### 3. Initialize & Run Application
```bash
# Start the Flask web application and background threads
python -m flask run --host=0.0.0.0 --port=5000
```
Access the dashboard at `http://localhost:5000` and login with your configured credentials.

---

## 3. Docker & Docker Compose Deployment

CortexCICD provides production-ready multi-container orchestration defined in `docker/docker-compose.yml`.

```mermaid
graph TD
    subgraph Docker Network: cortex-net
        API[cortex-api:5000]
        Worker[cortex-worker: background tasks]
        DB[(PostgreSQL / SQLite)]
        Prom[Prometheus:9090]
        Graf[Grafana:3000]
    end

    User([Operator / Developer]) -->|HTTP 5000| API
    User -->|HTTP 3000| Graf
    API --> DB
    Worker --> DB
    Prom -->|Scrape metrics| API
    Graf -->|PromQL| Prom
```

### 1. Start Services via Docker Compose
```bash
cd docker
docker compose up -d --build
```

### 2. Verify Running Containers
```bash
docker compose ps
```
Services exposed:
- **Cortex API & Web UI:** `http://localhost:5000`
- **Prometheus UI:** `http://localhost:9090`
- **Grafana UI:** `http://localhost:3000` (Default credentials: `admin` / `admin`)

---

## 4. Kubernetes Cluster Deployment

Production Kubernetes manifests are located in `kubernetes/`:

### 1. Configure RBAC Permissions for the Self-Healing Engine
The self-healing engine requires Kubernetes RBAC permissions to inspect and delete pods, roll back deployments, and adjust replica counts:
```bash
kubectl apply -f kubernetes/healing-rbac.yaml
```
*`healing-rbac.yaml` defines a `ServiceAccount` (`cortex-healing-sa`), `ClusterRole`, and `ClusterRoleBinding` granting access to `pods`, `deployments`, `replicasets`, and `events`.*

### 2. Deploy Cortex Application & Service
```bash
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
```

### 3. Verify Pod & Health Probes
```bash
kubectl get pods -l app=cortex-api
kubectl describe pod -l app=cortex-api
```
*Health probes automatically query `/healthz` (liveness) and `/readyz` (readiness).*

---

## 5. Observability Setup: Prometheus & Grafana

### 1. Prometheus Telemetry Scraping
The configuration in `monitoring/prometheus.yml` scrapes the Cortex application metrics endpoint:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'cortex-api'
    metrics_path: '/api/prometheus/metrics'
    static_configs:
      - targets: ['cortex-api:5000']
```

### 2. Pre-Configured Grafana Dashboard
Import `monitoring/grafana-dashboard.json` into Grafana to instantly visualize:
- Total pipeline runs and success/failure ratios
- Self-healing recovery resolution rate
- Active alerts categorized by severity
- Pod memory and CPU saturation graphs

---

## 6. Jenkins Pipeline Integration

### 1. Shared Pipeline Library (`jenkins/cortex-plugin.groovy`)
Place `cortex-plugin.groovy` in your Jenkins global pipeline library to enable failure interception steps:
- `cortexWatch { ... }`: Wraps build stages to capture stderr and execution durations.
- `cortexReportFailure { ... }`: Automatically transmits failure payloads to `http://<cortex-api>/webhooks/jenkins`.

### 2. Example Jenkinsfile (`jenkins/Jenkinsfile.example`)
Include post-build failure hooks in your target project repositories:
```groovy
post {
    failure {
        cortexReportFailure(
            webhook: 'http://cortex-api.cortex-system.svc.cluster.local/webhooks/jenkins',
            extractLogs: true,
            autoHeal: true
        )
    }
}
```

---

## 7. Environment Variables Reference

| Variable | Default Value | Purpose |
| :--- | :--- | :--- |
| `FLASK_APP` | `app/app.py` | Flask entry point. |
| `SECRET_KEY` | `cortex-secret-key-change-in-production` | Secret used to sign session cookies. |
| `ADMIN_USERNAME` | `admin` | Dashboard login username. |
| `ADMIN_PASSWORD` | `admin123` | Dashboard login password. |
| `DATABASE_URL` | `sqlite:///app/cortex.db` | SQLAlchemy database connection URI. |
| `JENKINS_URL` | `""` (Empty = mock mode) | URL of upstream Jenkins server. |
| `JENKINS_USER` | `""` | Jenkins HTTP authentication user. |
| `JENKINS_TOKEN` | `""` | Jenkins API user token. |
| `K8S_KUBECONFIG`| `~/.kube/config` | File path to Kubernetes config. |
| `K8S_NAMESPACE` | `default` | Target Kubernetes namespace for healing. |
| `PROMETHEUS_URL`| `http://localhost:9090` | Prometheus server base URL. |
| `GITHUB_WEBHOOK_SECRET` | `""` | Secret key for validating GitHub webhook HMAC signatures. |
| `SLACK_WEBHOOK_URL` | `""` | Incoming Slack webhook for escalation notifications. |
| `SMTP_SERVER` | `""` | Outbound SMTP relay server hostname. |

