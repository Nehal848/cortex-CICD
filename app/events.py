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
import queue
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock        = threading.Lock()
_subscribers: dict[int, queue.Queue] = {}
_id_counter  = 0

_MAX_CLIENTS = 50   # maximum concurrent SSE connections
_QUEUE_SIZE  = 100  # events buffered per client before dropping


def subscribe() -> tuple[int, queue.Queue]:
    """
    Register a new SSE client.

    Returns
    -------
    (client_id, event_queue)
        client_id  — unique integer, pass to unsubscribe() on disconnect
        event_queue — Queue of {"event": str, "data": str} dicts
    """
    global _id_counter
    with _lock:
        if len(_subscribers) >= _MAX_CLIENTS:
            raise RuntimeError(f"SSE client limit ({_MAX_CLIENTS}) reached.")
        _id_counter += 1
        sub_id = _id_counter
        q = queue.Queue(maxsize=_QUEUE_SIZE)
        _subscribers[sub_id] = q
        logger.debug("[SSE] Client %d connected. Active: %d", sub_id, len(_subscribers))
        return sub_id, q


def unsubscribe(sub_id: int):
    """Remove a disconnected SSE client."""
    with _lock:
        _subscribers.pop(sub_id, None)
        logger.debug("[SSE] Client %d disconnected. Active: %d", sub_id, len(_subscribers))


def publish(event_type: str, payload: dict):
    """
    Broadcast an event to all connected SSE clients.
    Clients with full queues are silently dropped.

    Parameters
    ----------
    event_type : str  e.g. "pipeline.updated", "alert.created"
    payload    : dict  JSON-serialisable event body
    """
    with _lock:
        subs = list(_subscribers.items())

    if not subs:
        return  # fast-path: no active clients

    message = {
        "event":     event_type,
        "payload":   payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data_str = json.dumps(message)
    item     = {"event": event_type, "data": data_str}

    dead: list[int] = []
    for sub_id, q in subs:
        try:
            q.put_nowait(item)
        except queue.Full:
            logger.warning("[SSE] Client %d queue full — dropping.", sub_id)
            dead.append(sub_id)

    for sub_id in dead:
        unsubscribe(sub_id)

    logger.debug("[SSE] Published '%s' to %d client(s).",
                 event_type, len(subs) - len(dead))


def subscriber_count() -> int:
    """Return the current number of active SSE connections."""
    with _lock:
        return len(_subscribers)
