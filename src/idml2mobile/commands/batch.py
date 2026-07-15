"""`batch` command — convert every IDML package folder under a root."""
from __future__ import annotations

from pathlib import Path
from typing import List

from idml2mobile.commands.base import Command
from idml2mobile.commands.convert import ConvertCommand
from idml2mobile.config import ConversionConfig, MobileProfile


class BatchCommand(Command):
    def __init__(self, input_root: Path, output_root: Path,
                 profile: MobileProfile = None, render_pdf: bool = True) -> None:  # type: ignore[assignment]
        super().__init__()
        self.input_root = Path(input_root)
        self.output_root = Path(output_root)
        self.profile = profile or MobileProfile()
        self.render_pdf = render_pdf

    def _discover(self) -> List[Path]:
        """Every folder containing at least one .idml (recursively), plus loose
        .idml files directly under the root."""
        found = set()
        for idml in self.input_root.rglob("*.idml"):
            found.add(idml.parent)
        return sorted(found)

    def execute(self) -> int:
        jobs = self._discover()
        if not jobs:
            print(f"No .idml packages found under {self.input_root}")
            return 1
        rc = 0
        for folder in jobs:
            name = folder.name or folder.parent.name
            out = self.output_root / name
            print(f"\n=== Converting {folder} -> {out} ===")
            config = ConversionConfig(
                input_path=folder, output_dir=out,
                profile=self.profile, render_pdf=self.render_pdf,
            )
            cmd = ConvertCommand(config)
            cmd.subject_hooks = list(self.subject_hooks)
            try:
                rc = max(rc, cmd.execute())
            except Exception as exc:  # keep batch going on a single failure
                print(f"FAILED {folder}: {exc}")
                rc = max(rc, 1)
        return rc
