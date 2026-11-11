from datetime import datetime
from .db import db


class PipelineRun(db.Model):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        db.Index("idx_pipeline_runs_repo_branch_created", "repo", "branch", "created_at"),
    )

    id          = db.Column(db.Integer, primary_key=True)
    run_id      = db.Column(db.String(20), unique=True, nullable=False)  # e.g. RUN-4819
    repo        = db.Column(db.String(120), nullable=False)
    branch      = db.Column(db.String(80), nullable=False)
    status      = db.Column(db.String(20), nullable=False)               # Success | Failed | Healed | In Progress
    triggered_by = db.Column(db.String(40), nullable=False)              # GitPush | Manual | Scheduled
    duration_secs = db.Column(db.Integer, default=0)
    risk_score  = db.Column(db.Integer, default=0)                       # 0-100
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    # Jenkins integration — set when a real build is triggered
    jenkins_build_number = db.Column(db.Integer, nullable=True)          # e.g. 142
    jenkins_job_name     = db.Column(db.String(120), nullable=True)      # e.g. CortexCICD/Self-Healing-CI-CD

    # Diff / commit telemetry (used by live ML prediction & retraining)
    files_changed  = db.Column(db.Integer, default=10)
    commit_message = db.Column(db.String(255), nullable=True)

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
    status     = db.Column(db.String(20), nullable=False)   # Active | Acknowledged | Silenced | Resolved | Archived
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Lifecycle tracking fields (v1.2)
    acknowledged_by = db.Column(db.String(60),   nullable=True)
    acknowledged_at = db.Column(db.DateTime,     nullable=True)
    resolved_by     = db.Column(db.String(60),   nullable=True)
    resolved_at     = db.Column(db.DateTime,     nullable=True)
    silenced_until  = db.Column(db.DateTime,     nullable=True)

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


class User(db.Model):
    """Application user account with hashed password and optional API token hash."""
    __tablename__ = "users"

    id                   = db.Column(db.Integer, primary_key=True)
    username             = db.Column(db.String(80), unique=True, nullable=False)
    password_hash        = db.Column(db.String(255), nullable=False)
    role                 = db.Column(db.String(30), default="admin")
    api_token_hash       = db.Column(db.String(128), nullable=True)
    api_token_expires_at = db.Column(db.DateTime, nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)


class PlatformSetting(db.Model):
    """Persisted key-value platform configuration editable from /settings."""
    __tablename__ = "platform_settings"

    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(80), unique=True, nullable=False)
    value      = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_value(cls, key: str, default: str | None = None) -> str | None:
        """Read a persisted setting inside an active app context, or return default."""
        try:
            row = cls.query.filter_by(key=key).first()
            return row.value if row is not None else default
        except Exception:
            return default

    @classmethod
    def get_bool(cls, key: str, default: bool = True) -> bool:
        """Read a boolean persisted setting safely."""
        val = cls.get_value(key)
        if val is None:
            return default
        return str(val).strip().lower() in ("true", "1", "yes", "on")
