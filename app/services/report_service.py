from app.models import PipelineRun, HealingEvent, Alert, Deployment
from reports.generator import generate_pipeline_report, generate_healing_report, generate_ai_report
from app.services.prediction_service import get_prediction_for_run, analyze_failure

def build_pipeline_report():
    runs_q  = PipelineRun.query.order_by(PipelineRun.created_at.desc()).limit(50).all()
    total   = PipelineRun.query.count()
    failed  = PipelineRun.query.filter_by(status="Failed").count()
    healed  = PipelineRun.query.filter_by(status="Healed").count()
    success = PipelineRun.query.filter_by(status="Success").count()
    stats   = {"total_runs": total, "failed": failed, "healed": healed,
               "success_rate": round((success + healed) / total * 100, 1) if total else 0,
               "active_alerts": Alert.query.filter_by(status="Active").count(),
               "total_deps":    Deployment.query.count()}
    runs_data = [{"run_id": r.run_id, "branch": r.branch, "status": r.status,
                  "triggered_by": r.triggered_by, "duration_secs": r.duration_secs,
                  "risk_score": r.risk_score} for r in runs_q]

    data, mime = generate_pipeline_report(runs_data, stats)
    ext = "pdf" if "pdf" in mime else "json"
    return data, mime, ext

def build_healing_report():
    events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).limit(50).all()
    events_data = [{"run_id": e.run_id, "failure_type": e.failure_type,
                    "strategy": e.strategy, "outcome": e.outcome,
                    "created_at": str(e.created_at)} for e in events]
    data, mime = generate_healing_report(events_data)
    ext = "pdf" if "pdf" in mime else "json"
    return data, mime, ext

def build_ai_report(run_id: str):
    run = PipelineRun.query.filter_by(run_id=run_id).first()
    if not run:
        raise ValueError("Run not found")

    prediction = get_prediction_for_run(run_id)
    rca = analyze_failure(prediction.get("failure_type", ""), "", run_id, 0, run.risk_score)
    data, mime = generate_ai_report(run_id, prediction, rca)
    ext = "pdf" if "pdf" in mime else "json"
    return data, mime, ext
