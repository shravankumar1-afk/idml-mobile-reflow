"""`inspect` command — report package structure without converting."""
from __future__ import annotations

import json
from pathlib import Path

from idml2mobile.commands.base import Command
from idml2mobile.idml.package import IDMLPackage
from idml2mobile.idml.validator import InputValidator
from idml2mobile.parsers.factory import ParserFactory


class InspectCommand(Command):
    def __init__(self, input_path: Path, as_json: bool = False) -> None:
        super().__init__()
        self.input_path = Path(input_path)
        self.as_json = as_json

    def execute(self) -> int:
        validation = InputValidator().validate(self.input_path)
        summary = validation.as_dict()

        if validation.idml_file:
            pkg = IDMLPackage(validation.idml_file)
            try:
                pkg.unpack()
                pages, frames = 0, 0
                threaded = False
                double_col = False
                for name in pkg.spread_order():
                    path = pkg.root / "Spreads" / name
                    if not path.exists():
                        continue
                    p, f = ParserFactory.for_spread(path).parse()
                    pages += len(p)
                    frames += len(f)
                    threaded = threaded or any(x.next_frame or x.prev_frame for x in f)
                    double_col = double_col or any(x.column_count >= 2 for x in f)
                summary["stats"] = {
                    "stories": len(pkg.stories()),
                    "spreads": len(pkg.spreads()),
                    "pages": pages,
                    "frames": frames,
                    "threaded": threaded,
                    "double_column_frames": double_col,
                }
            finally:
                pkg.cleanup()

        if self.as_json:
            print(json.dumps(summary, indent=2))
        else:
            self._pretty(summary)
        return 0 if validation.ok else 1

    @staticmethod
    def _pretty(summary: dict) -> None:
        print(f"IDML:          {summary.get('idml_file')}")
        print(f"Reference PDF: {summary.get('reference_pdf')}")
        print(f"Links dir:     {summary.get('links_dir')}")
        print(f"Fonts dir:     {summary.get('fonts_dir')}")
        print(f"Fonts:         {len(summary.get('fonts', []))}")
        print(f"Links present: {len(summary.get('present_links', []))}")
        print(f"Links missing: {len(summary.get('missing_links', []))}")
        for m in summary.get("missing_links", [])[:20]:
            print(f"   - MISSING {m}")
        stats = summary.get("stats")
        if stats:
            print("Stats:")
            for k, v in stats.items():
                print(f"   {k}: {v}")
        for w in summary.get("warnings", []):
            print(f"WARNING: {w}")
