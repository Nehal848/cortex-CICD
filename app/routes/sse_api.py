import io
import queue
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from app.auth_guard import _auth
from app.http_security import get_client_ip

sse_api_bp = Blueprint('sse_api', __name__, url_prefix="/api")


@sse_api_bp.route("/stream")
def sse_stream():
    """
    Server-Sent Events endpoint.
    Returns a persistent text/event-stream connection that pushes
    real-time events to the browser without page refresh.

    Authentication: session cookie or Bearer token.
    Disconnect: close the browser tab or EventSource.close().
    """
    auth = _auth()
    if auth:
        return auth

    from app.events import subscribe, unsubscribe
    import json as _json

    client_ip = get_client_ip()
    try:
        sub_id, q = subscribe(client_ip)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 429

    @stream_with_context
    def _generate():
        # Initial connection event
        yield f"event: connected\ndata: {_json.dumps({'message': 'SSE stream connected', 'client_id': sub_id})}\n\n"
        try:
            while True:
                try:
                    item = q.get(timeout=30)
                    yield f"event: {item['event']}\ndata: {item['data']}\n\n"
                except queue.Empty:
                    # Heartbeat comment keeps the connection alive through proxies
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            unsubscribe(sub_id)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx response buffering
            "Connection":       "keep-alive",
        },
    )


@sse_api_bp.route("/reports/pipeline")
def report_pipeline():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_pipeline_report
        data, mime, ext = build_pipeline_report()
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_pipeline_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@sse_api_bp.route("/reports/healing")
def report_healing():
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_healing_report
        data, mime, ext = build_healing_report()
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_healing_report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@sse_api_bp.route("/reports/ai/<run_id>")
def report_ai(run_id):
    auth = _auth()
    if auth:
        return auth
    try:
        from app.services.report_service import build_ai_report
        data, mime, ext = build_ai_report(run_id)
        return send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f"cortex_ai_report_{run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{ext}")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
