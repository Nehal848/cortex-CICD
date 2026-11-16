from flask import Blueprint, jsonify, request

from app.auth_guard import _auth, check_role

pipeline_api_bp = Blueprint('pipeline_api', __name__, url_prefix="/api")


@pipeline_api_bp.route("/pipeline/run", methods=["POST"])
def run_pipeline():
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    data = request.json or {}
    from app.validation import validate_pipeline_run
    cleaned, errors = validate_pipeline_run(data)
    if errors:
        return jsonify({"errors": errors}), 400
    from app.services.pipeline_service import trigger_pipeline
    result = trigger_pipeline(cleaned["job_name"], cleaned["branch"])

    run = result["run"]
    return jsonify({
        "success": True,
        "message": result["message"],
        "mock": result["mock"],
        "jenkins_result": result["jenkins_result"],
        "run": {
            "id": run.run_id,
            "repo": run.repo,
            "branch": run.branch,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "timestamp": run.timestamp,
        }
    })


@pipeline_api_bp.route("/stats")
def api_stats():
    auth = _auth()
    if auth:
        return auth
    from app.services.pipeline_service import get_dashboard_stats
    return jsonify(get_dashboard_stats())


@pipeline_api_bp.route("/predict/<run_id>")
def api_predict(run_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.prediction_service import get_prediction_for_run
        return jsonify(get_prediction_for_run(run_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@pipeline_api_bp.route("/ml/retrain", methods=["POST"])
def api_ml_retrain():
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("admin")
    if role_err:
        return role_err
    try:
        from ml.predict_failure import retrain_from_database
        min_samples = int((request.json or {}).get("min_samples", 5))
        return jsonify(retrain_from_database(min_samples=min_samples))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@pipeline_api_bp.route("/analyze", methods=["POST"])
def api_analyze():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.validation import validate_analyze
        cleaned, errors = validate_analyze(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        from app.services.prediction_service import analyze_failure
        return jsonify(analyze_failure(
            cleaned["failure_type"],
            cleaned["log_snippet"],
            cleaned["run_id"],
            cleaned["pod_restarts"],
            cleaned["risk_score"],
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@pipeline_api_bp.route("/heal/<run_id>", methods=["POST"])
def api_heal(run_id):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.services.healing_service import trigger_healing_now
        return jsonify(trigger_healing_now(run_id, request.json or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@pipeline_api_bp.route("/healing/status")
def api_healing_status():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.healing_service import get_healing_status
        return jsonify(get_healing_status())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
