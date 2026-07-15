"""EquationMap — basename -> LaTeX transcription of a MathType equation.

The map lives in a bundled JSON file (`resources/equations.json`) keyed by the
WMF/EPS basename as it appears in the IDML `LinkResourceURI` (case-insensitive).
Each value is either a LaTeX string, or an object ``{"latex": "...", "display":
true|false}``. ``display`` forces block vs inline rendering; when omitted the
renderer decides from context (a stand-alone equation paragraph is display).

Transcriptions are produced offline (vision transcription of the rendered
equation image, verified against it) and can be corrected by editing the JSON —
one equation per key, so a single wrong equation is a one-line fix. Any equation
with no entry (or an empty ``latex``) falls back to its original image, so the
output is never broken or missing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "resources" / "equations.json"


@dataclass(frozen=True)
class EquationLatex:
    latex: str
    display: Optional[bool] = None  # None => let the renderer decide from context


class EquationMap:
    def __init__(self, entries: Dict[str, EquationLatex]) -> None:
        # keys are stored lower-cased for robust matching
        self._entries = entries

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "EquationMap":
        p = Path(path) if path else _DEFAULT_PATH
        if not p.exists():
            return cls({})
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls({})
        entries: Dict[str, EquationLatex] = {}
        for key, val in (raw.get("equations", raw) or {}).items():
            if isinstance(val, str):
                latex, display = val, None
            elif isinstance(val, dict):
                latex, display = val.get("latex", ""), val.get("display")
            else:
                continue
            if latex and latex.strip():
                entries[key.strip().lower()] = EquationLatex(latex.strip(), display)
        return cls(entries)

    @staticmethod
    def _basename(ref: str) -> str:
        return Path(unquote(ref or "").replace("\\", "/")).name.strip().lower()

    def lookup(self, ref: str) -> Optional[EquationLatex]:
        """Look up by a LinkResourceURI or basename (case-insensitive)."""
        if not ref:
            return None
        return self._entries.get(self._basename(ref))

    def __len__(self) -> int:
        return len(self._entries)
