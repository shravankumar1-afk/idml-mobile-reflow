"""Concrete observers: a Rich console reporter and a plain file logger."""
from __future__ import annotations

import logging
from pathlib import Path

from idml2mobile.observers.base import Event, Level

try:  # rich is a hard dependency, but degrade gracefully if unavailable
    from rich.console import Console

    _console = Console()
except Exception:  # pragma: no cover
    _console = None


_STYLE = {
    Level.DEBUG: "dim",
    Level.INFO: "cyan",
    Level.WARNING: "yellow",
    Level.ERROR: "bold red",
}


class RichProgressObserver:
    """Prints human-friendly, colorized stage updates to the console."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def notify(self, event: Event) -> None:
        if event.level == Level.DEBUG and not self.verbose:
            return
        pct = f" [{event.progress * 100:5.1f}%]" if event.progress is not None else ""
        line = f"[{event.stage}]{pct} {event.message}"
        if _console is not None:
            _console.print(line, style=_STYLE.get(event.level, ""))
        else:  # pragma: no cover
            print(line)


class LoggingObserver:
    """Writes every event to a log file (useful for batch runs and CI)."""

    def __init__(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(f"idml2mobile.{log_path.stem}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._logger.addHandler(handler)

    def notify(self, event: Event) -> None:
        level = {
            Level.DEBUG: logging.DEBUG,
            Level.INFO: logging.INFO,
            Level.WARNING: logging.WARNING,
            Level.ERROR: logging.ERROR,
        }[event.level]
        self._logger.log(level, "[%s] %s", event.stage, event.message)
