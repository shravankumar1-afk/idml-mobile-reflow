"""AssetRepository â€” single source of truth for images.

Given a link URI from the IDML, it locates the file in the Links folder,
converts it to a web-safe form under output/images/, caches the result, and
records provenance (original ref + conversion method) for the QA report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

from idml2mobile.assets.convert import ConversionOutcome, convert_to_websafe


@dataclass
class AssetRecord:
    original_ref: str          # raw LinkResourceURI
    original_name: str         # basename as referenced
    found: bool
    converted: bool
    method: str = ""
    output_rel: str = ""       # path relative to output dir (e.g. images/foo.png)
    note: str = ""


@dataclass
class AssetRepository:
    links_dir: Optional[Path]
    output_dir: Path
    images_subdir: str = "images"
    _cache: Dict[str, AssetRecord] = field(default_factory=dict)

    @property
    def images_dir(self) -> Path:
        return self.output_dir / self.images_subdir

    def resolve(self, link_uri: str) -> AssetRecord:
        if link_uri in self._cache:
            return self._cache[link_uri]
        record = self._resolve_uncached(link_uri)
        self._cache[link_uri] = record
        return record

    def _resolve_uncached(self, link_uri: str) -> AssetRecord:
        name = Path(unquote(link_uri)).name
        stem = self._safe_stem(name)
        if not self.links_dir:
            return AssetRecord(link_uri, name, False, False, note="No Links folder")

        src = self.links_dir / name
        if not src.exists():
            # tolerate case / whitespace differences
            src = self._fuzzy_find(name)
        if src is None or not src.exists():
            return AssetRecord(link_uri, name, False, False, note="Link file not found")

        outcome: ConversionOutcome = convert_to_websafe(src, self.images_dir, stem)
        if outcome.ok and outcome.output_path is not None:
            rel = f"{self.images_subdir}/{outcome.output_path.name}"
            return AssetRecord(
                original_ref=link_uri,
                original_name=name,
                found=True,
                converted=outcome.method not in ("copy",),
                method=outcome.method,
                output_rel=rel,
            )
        return AssetRecord(
            link_uri, name, True, False, method=outcome.method, note=outcome.note
        )

    def records(self) -> List[AssetRecord]:
        return list(self._cache.values())

    def source_path(self, link_uri: str) -> Optional[Path]:
        """Locate a linked source without converting it."""
        if not self.links_dir:
            return None
        name = Path(unquote(link_uri)).name
        direct = self.links_dir / name
        return direct if direct.exists() else self._fuzzy_find(name)

    def _fuzzy_find(self, name: str) -> Optional[Path]:
        target = name.lower().strip()
        for p in self.links_dir.glob("*"):
            if p.name.lower().strip() == target:
                return p
        return None

    @staticmethod
    def _safe_stem(name: str) -> str:
        stem = Path(name).stem
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_") or "asset"

