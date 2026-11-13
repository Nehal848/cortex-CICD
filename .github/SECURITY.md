# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |

## Reporting a Vulnerability

We take the security of **CortexCICD** seriously. If you discover a security vulnerability, please do not disclose it publicly or open a public GitHub issue.

### Disclosure Process
1. Email details of the issue to **security@cortex-cicd.internal** (or contact repository maintainers via private GitHub Security Advisory).
2. Include reproduction steps, sample payload, and potential impact.
3. You will receive an acknowledgment within **48 hours**, followed by status updates as the patch is prepared.

## Security Architecture & Best Practices

- **Production Mode:** Always run with `FLASK_ENV=production`, a random `SECRET_KEY` of at least 32 characters, and `SESSION_COOKIE_SECURE=true` behind a TLS-terminating reverse proxy.
- **Webhook Hardening:** Set `STRICT_WEBHOOK_VERIFICATION=true`, `GITHUB_WEBHOOK_SECRET`, `JENKINS_WEBHOOK_SECRET`, and `ALERTMANAGER_TOKEN` so all inbound webhooks fail closed without valid tokens.
- **Trusted Execution Environment (TEE):** In standard development and testing, TEE runs in `TEE_MODE=simulated` using software AES-256-GCM authenticated encryption. For hardware enclave guarantees, deploy inside AWS Nitro Enclaves, Intel SGX, or AMD SEV confidential VM environments.

