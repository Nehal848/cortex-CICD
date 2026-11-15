# Contributing to CortexCI/CD

Thank you for your interest in contributing to CortexCI/CD! This guide details our workflow, standards, and setup instructions.

---

## Quick Start

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Nehal848/cortex-CICD.git
   cd cortex-CICD
   ```

2. **Set Up Virtual Environment**
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Run the Test Suite**
   ```bash
   python tests/run_tests.py
   ```

---

## Running Tests

All unit, integration, and security checks are executed through the central test runner:

```bash
python tests/run_tests.py
```

Alternatively, run specific tests using pytest:

```bash
pytest tests/ -v
```

Ensure all tests pass before opening a pull request.

---

## Branch Naming

Follow structured branch naming prefixes based on the nature of the change:

- `feat/<feature-name>`: New capabilities or functional enhancements (e.g., `feat/prometheus-alerts`)
- `fix/<bug-name>`: Bug fixes and security patches (e.g., `fix/auth-token-expiry`)
- `docs/<doc-name>`: Documentation additions or updates (e.g., `docs/contributing-guide`)
- `chore/<task-name>`: Tooling, dependency maintenance, build scripts, or CI/CD pipelines (e.g., `chore/bump-dependencies`)

---

## Commit Format

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>(<scope>): <short description>
```

### Types:
- `feat:` A new feature
- `fix:` A bug fix
- `docs:` Documentation changes only
- `chore:` Changes to build process, dependency updates, or auxiliary tools
- `refactor:` Code change that neither fixes a bug nor adds a feature
- `test:` Adding or updating tests

### Examples:
- `feat(monitoring): add prometheus alert rules and grafana provisioning`
- `fix(auth): enforce secure session cookies and CSRF protection`
- `docs(readme): add build status badges and setup instructions`
- `chore(ci): update github actions workflow for coverage reporting`

---

## PR Checklist

Before submitting a Pull Request, verify:

- [ ] All tests pass locally via `python tests/run_tests.py`.
- [ ] No broken imports or syntax errors across any module.
- [ ] New code follows existing architecture and style conventions.
- [ ] Relevant documentation (README, architecture docs, inline docstrings) has been updated.
- [ ] Commits follow the conventional commit format.
- [ ] Sensitive information, credentials, or debug flags are not committed.

---

## Architecture Overview

CortexCI/CD is an autonomous self-healing continuous integration and deployment engine:

1. **Ingestion & Webhooks**: Webhooks from Git providers (GitHub, GitLab) or CI runners (Jenkins) are ingested by the Flask API server (`app/`).
2. **Pipeline Execution & Telemetry**: Pipelines run containerized jobs while emitting real-time telemetry (SSE events and Prometheus metrics) tracked in `app/observability.py`.
3. **Failure Analysis & ML Diagnosis**: When a stage fails, the failure analysis engine captures logs and features (`ml/feature_extractor.py`), querying the trained diagnosis model (`ml/predict_failure.py`) to classify root causes (OOM, timeout, dependency issues, etc.).
4. **Autonomous Self-Healing**: The healing engine triggers configured recovery strategies (container restart, dependency cache prune, configuration retry, or rollback). Escalations occur if autonomous recovery thresholds are exceeded.
5. **Observability**: Prometheus scrapes metrics from the API and worker services, alerting via Alertmanager (`monitoring/alerts.yml`), visualized in Grafana dashboards (`monitoring/grafana-dashboard.json`).
