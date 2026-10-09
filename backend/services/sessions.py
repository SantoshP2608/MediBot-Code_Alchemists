"""Bounded, expiring anonymous sessions; serialize requests within each chat."""
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic

from backend.config.settings import CONSTANTS
from backend.services.conversation import Conversation


@dataclass
class Session:
    conversation: Conversation = field(default_factory=Conversation)
    lock: object = field(default_factory=Lock)
    replies: OrderedDict = field(default_factory=OrderedDict)
    touched: float = 0
    active: int = 0


class SessionCapacityError(Exception):
    pass


class SessionStore:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.sessions = {}
        self.lock = Lock()

    @contextmanager
    def acquire(self, session_id):
        config = CONSTANTS['api']
        with self.lock:
            now = self.clock()
            expired = [key for key, value in self.sessions.items()
                       if not value.active and now - value.touched >= config['session_ttl_seconds']]
            for key in expired:
                del self.sessions[key]
            if session_id not in self.sessions:
                if len(self.sessions) >= config['max_sessions']:
                    raise SessionCapacityError()
                self.sessions[session_id] = Session(touched=now)
            session = self.sessions[session_id]
            session.active += 1
        try:
            with session.lock:
                yield session
        finally:
            with self.lock:
                session.active -= 1
                session.touched = self.clock()
