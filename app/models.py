from datetime import datetime
from .db import db


class PipelineRun(db.Model):
    __tablename__ = "pipeline_runs"

    id          = db.Column(db.Integer, primary_key=True)
    run_id      = db.Column(db.String(20), unique=True, nullable=False)  # e.g. RUN-4819
    repo        = db.Column(db.String(120), nullable=False)
    branch      = db.Column(db.String(80), nullable=False)
    status      = db.Column(db.String(20), nullable=False)               # Success | Failed | Healed | In Progress
    triggered_by = db.Column(db.String(40), nullable=False)              # GitPush | Manual | Scheduled
    duration_secs = db.Column(db.Integer, default=0)
    risk_score  = db.Column(db.Integer, default=0)                       # 0-100
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    # Alias so templates can use run.timestamp (human-readable)
    @property
    def timestamp(self):
        delta = datetime.utcnow() - self.created_at
        secs  = int(delta.total_seconds())
        if secs < 60:
            return "Just now"
        elif secs < 3600:
            return f"{secs // 60} mins ago"
        elif secs < 86400:
            return f"{secs // 3600} hr{'s' if secs // 3600 > 1 else ''} ago"
        else:
            return self.created_at.strftime("%d %b %Y")


class Deployment(db.Model):
    __tablename__ = "deployments"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(80), nullable=False)
    environment = db.Column(db.String(30), nullable=False)   # Production | Staging | Dev
    version     = db.Column(db.String(30), nullable=False)
    status      = db.Column(db.String(20), nullable=False)   # Running | Stopped | Failed | Pending
    deployed_by = db.Column(db.String(60), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def timestamp(self):
        delta = datetime.utcnow() - self.created_at
        secs  = int(delta.total_seconds())
        if secs < 60:
            return "Just now"
        elif secs < 3600:
            return f"{secs // 60} mins ago"
        elif secs < 86400:
            return f"{secs // 3600} hr{'s' if secs // 3600 > 1 else ''} ago"
        else:
            return self.created_at.strftime("%d %b %Y")


class HealingEvent(db.Model):
    __tablename__ = "healing_events"

    id           = db.Column(db.Integer, primary_key=True)
    run_id       = db.Column(db.String(20), nullable=False)
    failure_type = db.Column(db.String(80), nullable=False)   # e.g. "Test Failure", "OOM", "Timeout"
    strategy     = db.Column(db.String(40), nullable=False)   # Auto Retry | Rollback | Pod Restart | Scale Up | Escalate
    outcome      = db.Column(db.String(20), nullable=False)   # Resolved | Failed | Escalated
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def timestamp(self):
        delta = datetime.utcnow() - self.created_at
        secs  = int(delta.total_seconds())
        if secs < 60:
            return "Just now"
        elif secs < 3600:
            return f"{secs // 60} mins ago"
        elif secs < 86400:
            return f"{secs // 3600} hr{'s' if secs // 3600 > 1 else ''} ago"
        else:
            return self.created_at.strftime("%d %b %Y")


class Alert(db.Model):
    __tablename__ = "alerts"

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(120), nullable=False)
    severity   = db.Column(db.String(20), nullable=False)   # Critical | High | Medium | Low
    source     = db.Column(db.String(60), nullable=False)
    status     = db.Column(db.String(20), nullable=False)   # Active | Resolved | Silenced
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def timestamp(self):
        delta = datetime.utcnow() - self.created_at
        secs  = int(delta.total_seconds())
        if secs < 60:
            return "Just now"
        elif secs < 3600:
            return f"{secs // 60} mins ago"
        elif secs < 86400:
            return f"{secs // 3600} hr{'s' if secs // 3600 > 1 else ''} ago"
        else:
            return self.created_at.strftime("%d %b %Y")
