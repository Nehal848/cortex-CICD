from app.models import HealingEvent

def trigger_healing_now(run_id: str, context: dict):
    from app.healing import scheduler
    return scheduler.trigger_now(run_id, context)

def get_healing_status():
    events = HealingEvent.query.order_by(HealingEvent.created_at.desc()).limit(20).all()
    return {
        "events": [
            {"run_id": e.run_id, "failure_type": e.failure_type,
             "strategy": e.strategy, "outcome": e.outcome,
             "timestamp": e.timestamp}
            for e in events
        ],
        "total": HealingEvent.query.count(),
        "resolved": HealingEvent.query.filter_by(outcome="Resolved").count(),
    }
