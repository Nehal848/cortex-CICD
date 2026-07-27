"""
tests/test_notifications.py
"""
import pytest
from app.notifications.dispatcher import notify
from app.services.notification_service import notify_security_issue


def test_notify_failure(monkeypatch):
    slack_calls = []
    email_calls = []
    
    import app.notifications.slack as slack
    import app.notifications.email as email
    
    monkeypatch.setattr(slack, "send_failure", lambda *args, **kwargs: slack_calls.append(args) or True)
    monkeypatch.setattr(email, "send_failure_email", lambda *args, **kwargs: email_calls.append(args) or True)

    notify(
        event_type="failure",
        payload={"run_id": "RUN-123", "failure_type": "Pipeline failed"}
    )
    
    assert len(slack_calls) == 1
    assert slack_calls[0][0] == "RUN-123"
    
    assert len(email_calls) == 1
    assert email_calls[0][0] == "RUN-123"


def test_notify_healed(monkeypatch):
    slack_calls = []
    import app.notifications.slack as slack
    monkeypatch.setattr(slack, "send_healed", lambda *args, **kwargs: slack_calls.append(args) or True)
    
    notify(event_type="healed", payload={"run_id": "RUN-124"})
    assert len(slack_calls) == 1
    assert slack_calls[0][0] == "RUN-124"


def test_notify_escalation(monkeypatch):
    slack_calls = []
    import app.notifications.slack as slack
    monkeypatch.setattr(slack, "send_escalation", lambda *args, **kwargs: slack_calls.append(args) or True)
    
    notify(event_type="escalation", payload={"run_id": "RUN-125"})
    assert len(slack_calls) == 1
    assert slack_calls[0][0] == "RUN-125"


def test_notify_security_issue(monkeypatch):
    slack_calls = []
    import app.notifications.slack as slack
    monkeypatch.setattr(slack, "send", lambda **kwargs: slack_calls.append(kwargs) or True)
    
    notify_security_issue("image:latest", critical=5, high=10)
    assert len(slack_calls) == 1
    msg = slack_calls[0]["message"]
    assert "image:latest" in msg
    assert "5 Critical" in msg
    assert slack_calls[0]["color"] == "danger"

