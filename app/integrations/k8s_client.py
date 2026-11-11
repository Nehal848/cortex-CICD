"""
Kubernetes Integration Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Wraps the official kubernetes Python client.
Falls back to realistic mock data if no kubeconfig is available.
"""

import os
import random
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_k8s_loaded = False


def _load_config():
    global _k8s_loaded
    if _k8s_loaded:
        return True
    try:
        from kubernetes import config as k8s_config
        kubeconfig = os.path.expanduser(os.getenv("K8S_KUBECONFIG", "~/.kube/config"))
        if os.path.exists(kubeconfig):
            k8s_config.load_kube_config(config_file=kubeconfig)
        else:
            k8s_config.load_incluster_config()
        _k8s_loaded = True
        logger.info("[K8s] Kubeconfig loaded.")
        return True
    except Exception as exc:
        logger.warning("[K8s] Could not load kubeconfig: %s — using mock.", exc)
        return False


def _namespace() -> str:
    return os.getenv("K8S_NAMESPACE", "default")


# ── Public API ─────────────────────────────────────────────────────

def list_pods(namespace: str | None = None) -> list[dict]:
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            v1 = k8s_client.CoreV1Api()
            pods = v1.list_namespaced_pod(namespace=ns)
            return [_format_pod(p) for p in pods.items]
        except Exception as exc:
            logger.error("[K8s] list_pods error: %s", exc)
    return _mock_pods()


def list_deployments(namespace: str | None = None) -> list[dict]:
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            apps = k8s_client.AppsV1Api()
            deps = apps.list_namespaced_deployment(namespace=ns)
            return [_format_deployment(d) for d in deps.items]
        except Exception as exc:
            logger.error("[K8s] list_deployments error: %s", exc)
    return _mock_deployments()


def list_services(namespace: str | None = None) -> list[dict]:
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            v1 = k8s_client.CoreV1Api()
            svcs = v1.list_namespaced_service(namespace=ns)
            return [_format_service(s) for s in svcs.items]
        except Exception as exc:
            logger.error("[K8s] list_services error: %s", exc)
    return _mock_services()


def list_nodes() -> list[dict]:
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            v1 = k8s_client.CoreV1Api()
            nodes = v1.list_node()
            return [_format_node(n) for n in nodes.items]
        except Exception as exc:
            logger.error("[K8s] list_nodes error: %s", exc)
    return _mock_nodes()


def restart_pod(pod_name: str, namespace: str | None = None) -> dict:
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            v1 = k8s_client.CoreV1Api()
            v1.delete_namespaced_pod(name=pod_name, namespace=ns)
            return {"success": True, "message": f"Pod {pod_name} deleted (will be restarted by deployment)."}
        except Exception as exc:
            logger.error("[K8s] restart_pod error: %s", exc)
            return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"[Mock] Pod {pod_name} restarted.", "mock": True}


def _deployment_revision(obj) -> int:
    """Extract numeric Kubernetes deployment revision annotation cleanly."""
    annotations = getattr(getattr(obj, "metadata", None), "annotations", None) or {}
    try:
        return int(annotations.get("deployment.kubernetes.io/revision", 0))
    except (TypeError, ValueError):
        return 0


def rollback_deployment(deployment_name: str, namespace: str | None = None) -> dict:
    """
    Roll back a Kubernetes Deployment using apps/v1 ReplicaSet history
    (``kubectl rollout undo`` equivalent; avoids deprecated ``spec.rollbackTo``).
    """
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            apps = k8s_client.AppsV1Api()
            dep = apps.read_namespaced_deployment(name=deployment_name, namespace=ns)
            current_rev = _deployment_revision(dep)

            match_labels = getattr(getattr(getattr(dep, "spec", None), "selector", None), "match_labels", None) or {"app": deployment_name}
            label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())
            rs_items = apps.list_namespaced_replica_set(namespace=ns, label_selector=label_selector).items

            owned_rs = []
            for rs in rs_items:
                owners = getattr(getattr(rs, "metadata", None), "owner_references", None) or []
                if owners and not any(o.kind == "Deployment" and o.name == deployment_name for o in owners):
                    continue
                rev = _deployment_revision(rs)
                if rev > 0:
                    owned_rs.append((rev, rs))

            owned_rs.sort(key=lambda pair: pair[0], reverse=True)
            prev_pair = next(((rev, rs) for rev, rs in owned_rs if current_rev == 0 or rev < current_rev), None)
            if current_rev == 0 and len(owned_rs) >= 2:
                prev_pair = owned_rs[1]
            elif current_rev == 0:
                prev_pair = None

            if not prev_pair:
                return {
                    "success": False,
                    "message": f"No previous ReplicaSet revision available to roll back {deployment_name}.",
                }

            target_rev, prev_rs = prev_pair
            body = {"spec": {"template": prev_rs.spec.template}}
            apps.patch_namespaced_deployment(name=deployment_name, namespace=ns, body=body)
            return {
                "success": True,
                "revision": target_rev,
                "message": f"Deployment {deployment_name} rolled back to revision {target_rev}.",
            }
        except Exception as exc:
            logger.error("[K8s] rollback_deployment error: %s", exc)
            return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"[Mock] Deployment {deployment_name} rolled back.", "mock": True}


def scale_deployment(deployment_name: str, replicas: int, namespace: str | None = None) -> dict:
    ns = namespace or _namespace()
    if _load_config():
        try:
            from kubernetes import client as k8s_client
            apps = k8s_client.AppsV1Api()
            body = {"spec": {"replicas": replicas}}
            apps.patch_namespaced_deployment(name=deployment_name, namespace=ns, body=body)
            return {"success": True, "message": f"Deployment {deployment_name} scaled to {replicas} replicas."}
        except Exception as exc:
            logger.error("[K8s] scale_deployment error: %s", exc)
            return {"success": False, "message": str(exc)}
    return {"success": True, "message": f"[Mock] Scaled {deployment_name} to {replicas} replicas.", "mock": True}


def get_cluster_summary() -> dict:
    pods = list_pods()
    nodes = list_nodes()
    running = sum(1 for p in pods if p["phase"] == "Running")
    pending = sum(1 for p in pods if p["phase"] == "Pending")
    failed = sum(1 for p in pods if p["phase"] == "Failed")
    ready_nodes = sum(1 for n in nodes if n["status"] == "Ready")
    return {
        "total_pods": len(pods),
        "running_pods": running,
        "pending_pods": pending,
        "failed_pods": failed,
        "total_nodes": len(nodes),
        "ready_nodes": ready_nodes,
    }


# ── Formatters ─────────────────────────────────────────────────────

def _format_pod(p) -> dict:
    restarts = 0
    if p.status.container_statuses:
        restarts = sum(c.restart_count for c in p.status.container_statuses)
    age = ""
    if p.metadata.creation_timestamp:
        delta = datetime.now(timezone.utc) - p.metadata.creation_timestamp
        h = int(delta.total_seconds() // 3600)
        age = f"{h}h" if h < 24 else f"{h // 24}d"
    return {
        "name": p.metadata.name,
        "namespace": p.metadata.namespace,
        "phase": p.status.phase or "Unknown",
        "restarts": restarts,
        "age": age,
        "node": p.spec.node_name or "",
        "ip": p.status.pod_ip or "",
    }


def _format_deployment(d) -> dict:
    return {
        "name": d.metadata.name,
        "namespace": d.metadata.namespace,
        "replicas": d.spec.replicas or 0,
        "ready": d.status.ready_replicas or 0,
        "available": d.status.available_replicas or 0,
        "image": d.spec.template.spec.containers[0].image if d.spec.template.spec.containers else "",
    }


def _format_service(s) -> dict:
    ports = []
    if s.spec.ports:
        ports = [f"{p.port}/{p.protocol}" for p in s.spec.ports]
    return {
        "name": s.metadata.name,
        "namespace": s.metadata.namespace,
        "type": s.spec.type,
        "cluster_ip": s.spec.cluster_ip or "",
        "external_ip": (s.status.load_balancer.ingress[0].ip
                        if s.status.load_balancer and s.status.load_balancer.ingress
                        else ""),
        "ports": ", ".join(ports),
    }


def _format_node(n) -> dict:
    status = "Unknown"
    if n.status.conditions:
        for cond in n.status.conditions:
            if cond.type == "Ready":
                status = "Ready" if cond.status == "True" else "NotReady"
    roles = [label.replace("node-role.kubernetes.io/", "")
             for label in (n.metadata.labels or {})
             if label.startswith("node-role.kubernetes.io/")]
    return {
        "name": n.metadata.name,
        "status": status,
        "roles": ", ".join(roles) or "worker",
        "cpu": n.status.capacity.get("cpu", "?"),
        "memory": n.status.capacity.get("memory", "?"),
        "os": n.status.node_info.os_image if n.status.node_info else "",
        "kubelet": n.status.node_info.kubelet_version if n.status.node_info else "",
    }


# ── Mock data ──────────────────────────────────────────────────────

def _mock_pods() -> list[dict]:
    return [
        {"name": "cortex-api-7d9f8b-xkq4p",     "namespace": "default", "phase": "Running",  "restarts": 0, "age": "2h",  "node": "node-01", "ip": "10.0.0.5"},
        {"name": "cortex-api-7d9f8b-m2lns",     "namespace": "default", "phase": "Running",  "restarts": 0, "age": "2h",  "node": "node-02", "ip": "10.0.0.6"},
        {"name": "healing-agent-5c6d7e-p9mnk",  "namespace": "default", "phase": "Running",  "restarts": 1, "age": "5h",  "node": "node-01", "ip": "10.0.0.7"},
        {"name": "ml-predictor-9a8b7c-tt3px",   "namespace": "default", "phase": "Running",  "restarts": 0, "age": "8h",  "node": "node-02", "ip": "10.0.0.8"},
        {"name": "cortex-worker-4f3e2d-zzq11",  "namespace": "default", "phase": "Pending",  "restarts": 3, "age": "1d",  "node": "node-01", "ip": ""},
        {"name": "prometheus-6b5c4d-k8s99",     "namespace": "monitoring", "phase": "Running","restarts": 0, "age": "2d",  "node": "node-02", "ip": "10.0.0.9"},
        {"name": "grafana-2a1b0c-tt88x",        "namespace": "monitoring", "phase": "Running","restarts": 0, "age": "2d",  "node": "node-02", "ip": "10.0.0.10"},
        {"name": "redis-cache-3c2d1e-pp77z",    "namespace": "default", "phase": "Running",  "restarts": 0, "age": "3d",  "node": "node-01", "ip": "10.0.0.11"},
    ]


def _mock_deployments() -> list[dict]:
    return [
        {"name": "cortex-api",      "namespace": "default",    "replicas": 2, "ready": 2, "available": 2, "image": "cortex-api:v2.4.1"},
        {"name": "healing-agent",   "namespace": "default",    "replicas": 1, "ready": 1, "available": 1, "image": "healing-agent:v1.0.4"},
        {"name": "ml-predictor",    "namespace": "default",    "replicas": 1, "ready": 1, "available": 1, "image": "ml-predictor:v0.9.2"},
        {"name": "cortex-worker",   "namespace": "default",    "replicas": 1, "ready": 0, "available": 0, "image": "cortex-worker:v2.5.0-rc1"},
        {"name": "prometheus",      "namespace": "monitoring", "replicas": 1, "ready": 1, "available": 1, "image": "prom/prometheus:latest"},
        {"name": "grafana",         "namespace": "monitoring", "replicas": 1, "ready": 1, "available": 1, "image": "grafana/grafana:latest"},
    ]


def _mock_services() -> list[dict]:
    return [
        {"name": "cortex-api-svc",    "namespace": "default",    "type": "ClusterIP",    "cluster_ip": "10.96.0.5",  "external_ip": "",           "ports": "5000/TCP"},
        {"name": "cortex-api-lb",     "namespace": "default",    "type": "LoadBalancer", "cluster_ip": "10.96.0.6",  "external_ip": "10.0.1.100", "ports": "80/TCP"},
        {"name": "healing-agent-svc", "namespace": "default",    "type": "ClusterIP",    "cluster_ip": "10.96.0.7",  "external_ip": "",           "ports": "8001/TCP"},
        {"name": "prometheus-svc",    "namespace": "monitoring", "type": "NodePort",     "cluster_ip": "10.96.0.20", "external_ip": "",           "ports": "9090:30090/TCP"},
        {"name": "grafana-svc",       "namespace": "monitoring", "type": "NodePort",     "cluster_ip": "10.96.0.21", "external_ip": "",           "ports": "3000:30300/TCP"},
        {"name": "redis-svc",         "namespace": "default",    "type": "ClusterIP",    "cluster_ip": "10.96.0.30", "external_ip": "",           "ports": "6379/TCP"},
        {"name": "kubernetes",        "namespace": "default",    "type": "ClusterIP",    "cluster_ip": "10.96.0.1",  "external_ip": "",           "ports": "443/TCP"},
    ]


def _mock_nodes() -> list[dict]:
    return [
        {"name": "node-01", "status": "Ready",    "roles": "control-plane, master", "cpu": "4", "memory": "8Gi",  "os": "Ubuntu 22.04", "kubelet": "v1.28.0"},
        {"name": "node-02", "status": "Ready",    "roles": "worker",                "cpu": "4", "memory": "8Gi",  "os": "Ubuntu 22.04", "kubelet": "v1.28.0"},
        {"name": "node-03", "status": "NotReady", "roles": "worker",                "cpu": "4", "memory": "16Gi", "os": "Ubuntu 22.04", "kubelet": "v1.28.0"},
    ]
