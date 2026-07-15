"""`convert` command."""
from __future__ import annotations

from idml2mobile.commands.base import Command
from idml2mobile.config import ConversionConfig
from idml2mobile.pipeline import ConversionPipeline


class ConvertCommand(Command):
    def __init__(self, config: ConversionConfig) -> None:
        super().__init__()
        self.config = config

    def execute(self) -> int:
        pipeline = ConversionPipeline(self.config)
        self._wire(pipeline)
        result = pipeline.convert()
        if result.qa is not None and not result.qa.passed:
            return 2  # completed, but QA flagged errors
        return 0
