"""`validate` command — run QA on an already-produced output/ folder."""
from __future__ import annotations

import json
from pathlib import Path

from idml2mobile.commands.base import Command
from idml2mobile.config import MobileProfile
from idml2mobile.qa.checks import QAValidator


class ValidateCommand(Command):
    def __init__(self, output_dir: Path, profile: MobileProfile = None) -> None:  # type: ignore[assignment]
        super().__init__()
        self.output_dir = Path(output_dir)
        self.profile = profile or MobileProfile()

    def execute(self) -> int:
        if not (self.output_dir / "index.html").exists():
            print(f"No index.html in {self.output_dir}")
            return 1
        report = QAValidator(self.profile).validate(
            self.output_dir, document=None, run_dynamic=True
        )
        print(json.dumps(report.as_dict(), indent=2))
        return 0 if report.passed else 2
