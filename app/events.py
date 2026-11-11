"""
SSE Event Bus
~~~~~~~~~~~~~
Thread-safe, in-process publish/subscribe for Server-Sent Events.

Publishers call publish() from anywhere in the app (healing engine,
pipeline service, alert service, status poller).

The SSE route (GET /api/stream) calls subscribe() to get a per-client
queue, reads events from it, and calls unsubscribe() on disconnect.

Architecture:
    publish("pipeline.updated", {...})
        └── puts item into every subscriber's Queue
                └── SSE generator reads & streams to browser

Constraints:
    • Max 50 concurrent SSE clients (_MAX_CLIENTS).
    • Each client queue holds 100 events; slow clients are dropped.
    • No external dependencies — stdlib only.
"""

import json
import logging
import os
import queue
import threading
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock        = threading.Lock()
_subscribers: dict[int, queue.Queue] = {}
_client_ips:  dict[int, str]         = {}
_id_counter  = 0

_MAX_CLIENTS = 50   # maximum concurrent SSE connections
_MAX_PER_IP  = 5    # maximum concurrent connections per IP address
_QUEUE_SIZE  = 100  # events buffered per client before dropping

_REDIS_CHANNEL = "cortex:events"
_INSTANCE_ID   = uuid.uuid4().hex[:12]
_redis_pub_client = None
_redis_sub_started = False


def _get_redis_url() -> str:
    return (os.getenv("REDIS_URL") or "").strip()


def _get_redis_client():
    global _redis_pub_client
    url = _get_redis_url()
    if not url:
        return None
    if _redis_pub_client is not None:
        return _redis_pub_client
    try:
        import redis
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        _redis_pub_client = client
        return client
    except Exception as exc:
        logger.debug("[SSE] Redis unavailable (%s) — using local queue only.", exc)
        return None


def _ensure_redis_listener() -> None:
    global _redis_sub_started
    if _redis_sub_started or not _get_redis_url():
        return
    with _lock:
        if _redis_sub_started:
            return
        _redis_sub_started = True

    def _listener_loop():
        import time
        while _get_redis_url():
            try:
                import redis
                client = redis.Redis.from_url(_get_redis_url(), decode_responses=True, socket_connect_timeout=2)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(_REDIS_CHANNEL)
                for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        envelope = json.loads(msg["data"])
                        if envelope.get("origin") == _INSTANCE_ID:
                            continue  # already delivered locally on publishing worker
                        _deliver_local(envelope["event"], envelope["data"])
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[SSE] Redis listener reconnecting: %s", exc)
                time.sleep(5)

    threading.Thread(target=_listener_loop, daemon=True, name="SSERedisListener").start()


def _deliver_local(event_type: str, data_str: str) -> None:
    with _lock:
        subs = list(_subscribers.items())
    if not subs:
        return

    item = {"event": event_type, "data": data_str}
    dead: list[int] = []
    for sub_id, q in subs:
        try:
            q.put_nowait(item)
        except queue.Full:
            logger.warning("[SSE] Client %d queue full — dropping.", sub_id)
            dead.append(sub_id)

    for sub_id in dead:
        unsubscribe(sub_id)

    logger.debug("[SSE] Delivered '%s' to %d local client(s).",
                 event_type, len(subs) - len(dead))


def subscribe(client_ip: str = "127.0.0.1") -> tuple[int, queue.Queue]:
    """
    Register a new SSE client with per-IP rate limiting.

    Returns
    -------
    (client_id, event_queue)
        client_id  — unique integer, pass to unsubscribe() on disconnect
        event_queue — Queue of {"event": str, "data": str} dicts
    """
    global _id_counter
    _ensure_redis_listener()
    with _lock:
        if len(_subscribers) >= _MAX_CLIENTS:
            raise RuntimeError(f"SSE client limit ({_MAX_CLIENTS}) reached.")

        current_ip_count = sum(1 for ip in _client_ips.values() if ip == client_ip)
        if current_ip_count >= _MAX_PER_IP:
            raise RuntimeError(f"Rate limit exceeded: max {_MAX_PER_IP} concurrent streams allowed per IP.")

        _id_counter += 1
        sub_id = _id_counter
        q = queue.Queue(maxsize=_QUEUE_SIZE)
        _subscribers[sub_id] = q
        _client_ips[sub_id]  = client_ip
        logger.debug("[SSE] Client %d (%s) connected. Active: %d", sub_id, client_ip, len(_subscribers))
        return sub_id, q


def unsubscribe(sub_id: int):
    """Remove a disconnected SSE client."""
    with _lock:
        _subscribers.pop(sub_id, None)
        _client_ips.pop(sub_id, None)
        logger.debug("[SSE] Client %d disconnected. Active: %d", sub_id, len(_subscribers))


def publish(event_type: str, payload: dict):
    """
    Broadcast an event to local SSE clients and (if configured) across
    all workers via Redis Pub/Sub channel ``cortex:events``.
    """
    redis_client = _get_redis_client()
    with _lock:
        has_local = bool(_subscribers)

    if not has_local and redis_client is None:
        return  # fast-path: no active clients and no distributed bus

    message = {
        "event":     event_type,
        "payload":   payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data_str = json.dumps(message)

    _deliver_local(event_type, data_str)

    if redis_client is not None:
        try:
            envelope = json.dumps({
                "origin": _INSTANCE_ID,
                "event": event_type,
                "data": data_str,
            })
            redis_client.publish(_REDIS_CHANNEL, envelope)
        except Exception as exc:
            logger.debug("[SSE] Redis publish failed: %s", exc)


def subscriber_count() -> int:
    """Return the current number of active SSE connections."""
    with _lock:
        return len(_subscribers)
