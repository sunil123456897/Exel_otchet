"""Thread-safe publish–subscribe event bus.

Events are published from any thread and drained from the GUI thread.
This decouples FileProcessor/AppController from GuiMaster — no more
4-layer callback chains for progress updates.
"""

import queue
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List


class EventType(Enum):
    PROGRESS_UPDATED = "progress_updated"
    OPERATION_STARTED = "operation_started"
    OPERATION_FINISHED = "operation_finished"
    ERROR_OCCURRED = "error_occurred"
    TITLE_REFRESH = "title_refresh"


@dataclass
class Event:
    type: EventType
    data: Any = None


class EventBus:
    _instance: "EventBus | None" = None

    def __init__(self) -> None:
        self._queue: queue.Queue[Event] = queue.Queue()
        self._listeners: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def publish(self, event: Event) -> None:
        self._queue.put(event)

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._listeners.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        with self._lock:
            listeners = self._listeners.get(event_type, [])
            if callback in listeners:
                listeners.remove(callback)

    def poll(self) -> None:
        """Drain the queue.  Must be called from the GUI thread."""
        try:
            while True:
                event = self._queue.get_nowait()
                with self._lock:
                    listeners = list(self._listeners.get(event.type, []))
                for cb in listeners:
                    try:
                        cb(event)
                    except Exception:
                        pass
                self._queue.task_done()
        except queue.Empty:
            pass
