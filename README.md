# Cortex CI/CD: The Self-Healing Pipeline 🧠

<div align="center">
  <h3>Deploy without fear. We heal the rest.</h3>
  <p>Cortex intercepts CI/CD failures in real-time, diagnoses the root cause, and autonomously writes the patch before you even notice.</p>
</div>

---

## 🚀 Overview

Cortex is a next-generation CI/CD monitoring and self-healing platform. Unlike traditional pipelines that simply fail and page a developer at 3 AM, Cortex uses heuristic modeling and AI agents to:
1. **Predict** failures before they happen using risk scoring.
2. **Intercept** pipeline crashes in real-time.
3. **Heal** the infrastructure autonomously (e.g., restarting pods, rolling back deployments, or generating code patches).

## ⚡ Features

- **Ultra-Premium Dashboard**: A stunning, glassmorphism UI built with vanilla CSS to monitor your deployments in real-time.
- **Predictive Risk Modeling**: Generates failure probabilities based on branch history and file changes.
- **Autonomous Healing Agents**: Integrates with Kubernetes RBAC to automatically scale, restart, or rollback failing deployments.
- **Jenkins Integration**: Plugs directly into your existing Jenkins pipelines via webhooks to intercept stack traces.

## 🛠️ Architecture

- **Backend**: Python, Flask, SQLAlchemy
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System), JS
- **Database**: SQLite (Development) -> PostgreSQL (Production)
- **Infrastructure Scaffolding**: Docker, Kubernetes, Jenkins, Prometheus, Grafana

## 📦 Getting Started

### 1. Run Locally (Docker)
The easiest way to spin up the Cortex API, Worker, Redis, and Prometheus is via Docker Compose:

```bash
docker-compose -f docker/docker-compose.yml up --build
```

### 2. Run Locally (Native Python)
If you want to run the Flask application natively:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the Flask app (will automatically seed the database)
python -m app.app
```
Navigate to `http://localhost:5000` to view the dashboard!

## 🔒 Security

Cortex requires RBAC permissions to heal Kubernetes clusters. Review the `kubernetes/healing-rbac.yaml` file to understand the scope of permissions granted to the AI Agent ServiceAccount.
