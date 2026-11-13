"""In-process event bus and single-use WebSocket tickets.

The bus is deliberately small: authenticated control channels receive only
events addressed to their own account. Tickets never authorize HTTP calls and
expire after sixty seconds.
"""
from __future__ import annotations

import queue
import secrets
import threading
import time


class EventBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers = {}

    def subscribe(self, user_id: str) -> queue.Queue:
        channel = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.setdefault(user_id, set()).add(channel)
        return channel

    def unsubscribe(self, user_id: str, channel: queue.Queue):
        with self._lock:
            channels = self._subscribers.get(user_id)
            if channels is not None:
                channels.discard(channel)
                if not channels:
                    self._subscribers.pop(user_id, None)

    def publish(self, user_ids, event: dict):
        with self._lock:
            targets = [(user, list(self._subscribers.get(user, ()))) for user in set(user_ids)]
        for _user, channels in targets:
            for channel in channels:
                try:
                    channel.put_nowait(dict(event))
                except queue.Full:
                    pass


class TicketStore:
    def __init__(self, ttl=60.0):
        self.ttl = float(ttl)
        self._lock = threading.RLock()
        self._tickets = {}

    def issue(self, user_id: str) -> dict:
        now = time.time()
        with self._lock:
            self._tickets = {token: item for token, item in self._tickets.items() if item["expires"] > now}
            token = secrets.token_urlsafe(32)
            self._tickets[token] = {"user_id": user_id, "expires": now + self.ttl}
            return {"ticket": token, "expires_in": int(self.ttl)}

    def consume(self, token: str):
        if not isinstance(token, str) or len(token) > 128:
            return None
        with self._lock:
            item = self._tickets.pop(token, None)
        if item is None or item["expires"] <= time.time():
            return None
        return item["user_id"]

    def __len__(self):
        with self._lock:
            return len(self._tickets)
