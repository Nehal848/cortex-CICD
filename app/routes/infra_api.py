from flask import Blueprint, jsonify, request

from app.auth_guard import _auth, check_role

infra_api_bp = Blueprint('infra_api', __name__, url_prefix="/api")


# --- PROMETHEUS ---
@infra_api_bp.route("/prometheus/metrics")
def prometheus_metrics():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.monitoring_service import get_all_metrics
        return jsonify(get_all_metrics())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/prometheus/http_rate")
def prometheus_http_rate():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.monitoring_service import get_http_rate
        return jsonify(get_http_rate())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- DOCKER ---
@infra_api_bp.route("/docker/containers")
def docker_containers():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify({"containers": dc.list_containers(all_containers=True), "summary": dc.get_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/docker/restart/<container_id>", methods=["POST"])
def docker_restart(container_id):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.restart_container(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/docker/remove/<container_id>", methods=["DELETE"])
def docker_remove(container_id):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.remove_container(container_id, force=True))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/docker/stats/<container_id>")
def docker_stats(container_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import docker_client as dc
        return jsonify(dc.get_container_stats(container_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- KUBERNETES ---
@infra_api_bp.route("/k8s/pods")
def k8s_pods():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"pods": k8s.list_pods(ns), "summary": k8s.get_cluster_summary()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/k8s/nodes")
def k8s_nodes():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        return jsonify({"nodes": k8s.list_nodes()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/k8s/deployments")
def k8s_deployments():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"deployments": k8s.list_deployments(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/k8s/services")
def k8s_services():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import k8s_client as k8s
        ns = request.args.get("namespace", None)
        return jsonify({"services": k8s.list_services(ns)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/k8s/restart/<pod_name>", methods=["POST"])
def k8s_restart_pod(pod_name):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.integrations import k8s_client as k8s
        ns = request.json.get("namespace", "default") if request.json else "default"
        return jsonify(k8s.restart_pod(pod_name, ns))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/k8s/scale/<deployment_name>", methods=["POST"])
def k8s_scale(deployment_name):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.integrations import k8s_client as k8s
        from app.validation import validate_k8s_scale
        cleaned, errors = validate_k8s_scale(request.json or {})
        if errors:
            return jsonify({"errors": errors}), 400
        return jsonify(k8s.scale_deployment(
            deployment_name, cleaned["replicas"], cleaned["namespace"]
        ))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- JENKINS ---
@infra_api_bp.route("/jenkins/jobs")
def jenkins_jobs():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"jobs": jc.get_all_jobs()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/jenkins/trigger/<path:job_name>", methods=["POST"])
def jenkins_trigger(job_name):
    auth = _auth()
    if auth:
        return auth
    role_err = check_role("operator")
    if role_err:
        return role_err
    try:
        from app.integrations import jenkins_client as jc
        return jsonify(jc.trigger_build(job_name, request.json or None))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@infra_api_bp.route("/jenkins/log/<path:job_name>/<int:build_num>")
def jenkins_log(job_name, build_num):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.integrations import jenkins_client as jc
        return jsonify({"log": jc.get_console_log(job_name, build_num)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
