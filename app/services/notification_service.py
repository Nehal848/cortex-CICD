def notify_security_issue(image: str, critical: int, high: int):
    try:
        from app.notifications import dispatcher
        dispatcher.notify("security", {
            "image":    image,
            "critical": critical,
            "high":     high,
        })
    except Exception:
        pass
