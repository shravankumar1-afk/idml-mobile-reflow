"""Command pattern for CLI actions.

Each CLI verb is a Command object with a uniform `execute()` returning a POSIX
exit code. The CLI layer only parses args and invokes commands, so the same
commands are reusable from tests or a future API without Click.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from idml2mobile.observers.base import Subject


class Command(ABC):
    def __init__(self) -> None:
        self.subject_hooks = []  # observers to attach to any Subject we create

    def attach_observer(self, observer) -> "Command":
        self.subject_hooks.append(observer)
        return self

    def _wire(self, subject: Subject) -> Subject:
        for obs in self.subject_hooks:
            subject.attach(obs)
        return subject

    @abstractmethod
    def execute(self) -> int:
        ...
