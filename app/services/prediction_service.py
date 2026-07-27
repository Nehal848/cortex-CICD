from app.models import PipelineRun


def _get_consecutive_failures(run: PipelineRun) -> int:
    """Query the DB for consecutive failures on the same repo+branch."""
    try:
        from app.services.pipeline_service import get_consecutive_failures
        return get_consecutive_failures(run.repo, run.branch)
    except Exception:
        return 0


def get_prediction_for_run(run_id: str):
    run = PipelineRun.query.filter_by(run_id=run_id).first()
    if not run:
        raise ValueError("Run not found")

    consec = _get_consecutive_failures(run)

    from ml.predict_failure import predict_failure_risk
    prediction = predict_failure_risk(
        repo=run.repo,
        branch=run.branch,
        files_changed=10,
        duration_secs=run.duration_secs,
        consecutive_failures=consec,
    )
    prediction["run_id"]              = run_id
    prediction["consecutive_failures"] = consec
    return prediction


def analyze_failure(failure_type: str, log_snippet: str, run_id: str, pod_restarts: int, risk_score: int):
    from ml.root_cause import analyze, analyze_risk_factors
    rca = analyze(failure_type, log_snippet, pod_restarts, risk_score)

    if run_id:
        run = PipelineRun.query.filter_by(run_id=run_id).first()
        if run:
            consec = _get_consecutive_failures(run)
            rca["risk_factors"] = analyze_risk_factors({
                "risk_score":          run.risk_score,
                "branch":              run.branch,
                "duration_secs":       run.duration_secs,
                "triggered_by":        run.triggered_by,
                "consecutive_failures": consec,
            })
            rca["consecutive_failures"] = consec

    rca["run_id"] = run_id
    return rca
