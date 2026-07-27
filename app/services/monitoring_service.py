def get_all_metrics():
    from app.integrations import prometheus_client as pc
    return pc.get_all_metrics()

def get_http_rate():
    from app.integrations import prometheus_client as pc
    return {
        "requests_per_sec": pc.get_http_request_rate(),
        "error_rate":       pc.get_error_rate(),
    }
