import os

from flask import Blueprint, jsonify, request

from app.auth_guard import _auth, check_role

security_api_bp = Blueprint('security_api', __name__, url_prefix="/api")


# --- TEE ---
@security_api_bp.route("/tee/status")
def tee_status():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import secrets as tee_secrets
        return jsonify(tee_secrets.get_tee_summary())
    except Exception as exc:
        return jsonify({"error": str(exc), "overall_status": "Error"}), 500


@security_api_bp.route("/tee/attestation")
def tee_attestation():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import attestation
        return jsonify(attestation.generate_attestation_report(request.args.get("nonce", None)))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@security_api_bp.route("/tee/seal", methods=["POST"])
def tee_seal():
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("admin")
    if role_err:
        return role_err
    try:
        data = request.json or {}
        if not data.get("key") or not data.get("value"):
            return jsonify({"error": "key and value required"}), 400
        from app.tee import secure_storage
        return jsonify({"success": secure_storage.store_secret(data["key"], data["value"]), "message": f"Secret '{data['key']}' sealed."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@security_api_bp.route("/tee/secrets")
def tee_secrets_list():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.tee import secure_storage
        return jsonify(secure_storage.get_store_info())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- SECURITY ---
@security_api_bp.route("/security/scan", methods=["POST"])
def security_scan():
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.validation import validate_security_scan
        cleaned, errors = validate_security_scan(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import scanner
        result = scanner.scan_image(cleaned["image"])
        if result.get("critical", 0) > 0:
            from app.services.notification_service import notify_security_issue
            notify_security_issue(cleaned["image"], result["critical"], result["high"])
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@security_api_bp.route("/security/secrets")
def security_secrets_scan():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.security import secret_scanner
        return jsonify(secret_scanner.scan_directory(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@security_api_bp.route("/security/sbom", methods=["POST"])
def security_sbom():
    """Generate an SBOM for a container image via Syft."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.validation import validate_security_scan, validate_sbom_format
        body = request.json or {}
        cleaned, errors = validate_security_scan(body)
        output_format, fmt_err = validate_sbom_format(body.get("format", "spdx-json"))
        if fmt_err:
            errors.append(fmt_err)
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import sbom
        return jsonify(sbom.generate_sbom(cleaned["image"], output_format))
    except Exception as exc:
        return jsonify({"error": "SBOM generation failed."}), 500


@security_api_bp.route("/security/cosign/verify", methods=["POST"])
def security_cosign_verify():
    """Verify cryptographic image signature via Cosign."""
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.validation import validate_security_scan, validate_cosign_public_key
        body = request.json or {}
        cleaned, errors = validate_security_scan(body)
        public_key, key_err = validate_cosign_public_key(body.get("public_key"))
        if key_err:
            errors.append(key_err)
        if errors:
            return jsonify({"errors": errors}), 400
        from app.security import cosign
        return jsonify(cosign.verify_image_signature(cleaned["image"], public_key))
    except Exception as exc:
        return jsonify({"error": "Signature verification failed."}), 500
