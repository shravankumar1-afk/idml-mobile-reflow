"""Observer pattern for progress + logging.

The pipeline is a `Subject`. Stages emit `Event`s; observers (console progress,
file logger, a GUI later) subscribe without the pipeline knowing who listens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Protocol


class Level(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Event:
    stage: str
    message: str
    level: Level = Level.INFO
    progress: float | None = None          # 0..1 for the current stage, or None
    data: Dict[str, Any] = field(default_factory=dict)


class Observer(Protocol):
    def notify(self, event: Event) -> None: ...


class Subject:
    """Mixin that lets any component broadcast events to attached observers."""

    def __init__(self) -> None:
        self._observers: List[Observer] = []

    def attach(self, observer: Observer) -> "Subject":
        self._observers.append(observer)
        return self

    def detach(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def emit(
        self,
        stage: str,
        message: str,
        level: Level = Level.INFO,
        progress: float | None = None,
        **data: Any,
    ) -> None:
        event = Event(stage=stage, message=message, level=level, progress=progress, data=data)
        for observer in self._observers:
            observer.notify(event)
