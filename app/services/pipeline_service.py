import threading
import time
import uuid
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app.db import db
from app.models import PipelineRun, Deployment, HealingEvent, Alert

_run_id_lock = threading.Lock()


def get_dashboard_stats():
    total   = PipelineRun.query.count()
    failed  = PipelineRun.query.filter_by(status="Failed").count()
    healed  = PipelineRun.query.filter_by(status="Healed").count()
    success = PipelineRun.query.filter_by(status="Success").count()
    rate    = round((success + healed) / total * 100, 1) if total else 0
    return {
        "total_runs":    total,
        "failed_builds": failed,
        "healed_runs":   healed,
        "success_rate":  rate,
        "total_deps":    Deployment.query.count(),
        "active_alerts": Alert.query.filter_by(status="Active").count(),
    }


def get_consecutive_failures(repo: str, branch: str) -> int:
    """
    Count the number of consecutive Failed/Healed runs immediately
    preceding the most recent Success on the same repo+branch.

    Example:
        RUN-31 Success
        RUN-32 Failed
        RUN-33 Failed   ← consecutive_failures = 2 for the next run
        RUN-34 Healed   ← (healed counts as "was failed")
        RUN-35 ?        ← consecutive_failures = 3
    """
    recent = (
        PipelineRun.query
        .filter_by(repo=repo, branch=branch)
        .filter(PipelineRun.status.in_(["Success", "Failed", "Healed"]))
        .order_by(PipelineRun.created_at.desc())
        .limit(20)
        .all()
    )
    count = 0
    for run in recent:
        if run.status == "Success":
            break
        # Failed or Healed both count as a bad run
        count += 1
    return count


def trigger_pipeline(
    job_name: str,
    branch: str,
    triggered_by: str = "Manual",
    files_changed: int = 10,
    commit_message: str | None = None,
):
    """
    Trigger a Jenkins build and create a PipelineRun record.

    Parameters
    ----------
    job_name     : Jenkins job name (also used as repo slug)
    branch       : git branch to build
    triggered_by : "Manual" | "GitPush" | "PullRequest" | "Scheduled"
    """
    jenkins_result   = {}
    jenkins_build_num = None

    try:
        from app.integrations import jenkins_client as jc
        jenkins_result = jc.trigger_build(job_name, {"BRANCH": branch} if branch else None)

        # Attempt to retrieve the queued build number (best-effort)
        if jenkins_result.get("success"):
            try:
                jobs = jc.get_all_jobs()
                matched = next((j for j in jobs if j["name"] == job_name), None)
                if matched:
                    jenkins_build_num = matched.get("last_build_number")
            except Exception:
                pass

    except Exception as exc:
        jenkins_result = {"success": False, "message": str(exc), "mock": True}

    consec = get_consecutive_failures(job_name, branch)
    computed_risk = 0
    try:
        from ml.predict_failure import predict_failure_risk
        pred = predict_failure_risk(
            repo=job_name,
            branch=branch,
            files_changed=files_changed or 10,
            duration_secs=0,
            consecutive_failures=consec,
        )
        computed_risk = int(pred.get("risk_score", 0))
    except Exception as exc:
        logger.warning("[Pipeline] Risk prediction fallback: %s", exc)

    new_run = None
    with _run_id_lock:
        # Find the highest numeric RUN-<N> suffix, skipping non-numeric IDs
        new_num = 4820
        all_runs = PipelineRun.query.filter(
            PipelineRun.run_id.like("RUN-%")
        ).all()
        for r in all_runs:
            try:
                n = int(r.run_id.split("-", 1)[1])
                if n >= new_num:
                    new_num = n + 1
            except (ValueError, IndexError):
                pass

        for attempt in range(5):
            candidate_id = (
                f"RUN-{new_num + attempt}"
                if attempt < 4
                else f"RUN-{int(time.time())}-{uuid.uuid4().hex[:4]}"
            )
            candidate_run = PipelineRun(
                run_id=candidate_id,
                repo=job_name,
                branch=branch,
                status="In Progress",
                triggered_by=triggered_by,
                duration_secs=0,
                risk_score=computed_risk,
                created_at=datetime.utcnow(),
                jenkins_build_number=jenkins_build_num,
                jenkins_job_name=job_name,
                files_changed=files_changed or 10,
                commit_message=(commit_message[:250] if commit_message else None),
            )
            db.session.add(candidate_run)
            try:
                db.session.commit()
                new_run = candidate_run
                break
            except IntegrityError:
                db.session.rollback()

    if new_run is None:
        raise RuntimeError("Failed to allocate unique pipeline run_id after retries")

    try:
        from app.observability import record_pipeline_event
        record_pipeline_event("In Progress", triggered_by)
    except Exception:
        pass

    # SSE: pipeline started
    try:
        from app.events import publish
        publish("pipeline.started", {
            "run_id":       new_run.run_id,
            "repo":         new_run.repo,
            "branch":       new_run.branch,
            "triggered_by": new_run.triggered_by,
        })
    except Exception:
        pass

    return {
        "message":        jenkins_result.get("message", "Pipeline run triggered."),
        "mock":           jenkins_result.get("mock", False),
        "jenkins_result": jenkins_result,
        "run":            new_run,
    }


def update_run_status(run_id: str, build_number: int, job_name: str) -> dict:
    """
    Poll Jenkins directly for a specific build and update the PipelineRun.
    Called from the API or the status poller for explicit resolution.

    Returns
    -------
    dict — {run_id, status, updated}
    """
    from app.integrations import jenkins_client as jc
    from app.healing import scheduler as healing_scheduler

    run = PipelineRun.query.filter_by(run_id=run_id).first()
    if not run:
        return {"error": f"Run {run_id} not found", "updated": False}

    if run.status != "In Progress":
        return {"run_id": run_id, "status": run.status, "updated": False,
                "reason": "already in terminal state"}

    build_info = jc.get_build_status(job_name, build_number)

    if build_info.get("building", False):
        return {"run_id": run_id, "status": "In Progress", "updated": False,
                "reason": "still building"}

    jenkins_result = build_info.get("result", "UNKNOWN")
    duration_ms    = build_info.get("duration_ms", 0)

    status_map = {"SUCCESS": "Success", "FAILURE": "Failed",
                  "ABORTED": "Failed", "UNSTABLE": "Failed"}
    new_status = status_map.get(jenkins_result.upper(), "Failed")

    run.status            = new_status
    run.duration_secs     = max(1, duration_ms // 1000) if duration_ms else run.duration_secs
    run.jenkins_build_number = build_number
    run.jenkins_job_name  = job_name

    db.session.add(run)
    db.session.commit()

    # SSE: pipeline updated
    try:
        from app.events import publish
        publish("pipeline.updated", {
            "run_id": run_id,
            "status": new_status,
            "duration_secs": run.duration_secs,
        })
    except Exception:
        pass

    if new_status == "Failed":
        try:
            healing_scheduler.trigger_now(run_id)
        except Exception:
            pass

    return {"run_id": run_id, "status": new_status, "updated": True}
