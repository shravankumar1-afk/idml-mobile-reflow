"""IDMLPackage — an IDML is a ZIP; this unpacks it and exposes its parts.

Provides lazy access to designmap.xml and the Stories / Spreads / Resources
directories, plus the story processing order declared in the designmap.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

from lxml import etree

IDPKG_NS = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"


class IDMLPackage:
    def __init__(self, idml_path: Path, workdir: Optional[Path] = None) -> None:
        self.idml_path = Path(idml_path)
        self._owns_workdir = workdir is None
        self.root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="idml2mobile_"))

    # -- lifecycle ---------------------------------------------------------
    def unpack(self) -> "IDMLPackage":
        if not zipfile.is_zipfile(self.idml_path):
            raise ValueError(f"Not a valid IDML (zip) file: {self.idml_path}")
        with zipfile.ZipFile(self.idml_path) as zf:
            zf.extractall(self.root)
        if not (self.root / "designmap.xml").exists():
            raise ValueError("designmap.xml missing — not a valid IDML package")
        return self

    def cleanup(self) -> None:
        if self._owns_workdir and self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> "IDMLPackage":
        return self.unpack()

    def __exit__(self, *exc) -> None:
        self.cleanup()

    # -- part access -------------------------------------------------------
    @property
    def designmap(self) -> Path:
        return self.root / "designmap.xml"

    def stories(self) -> List[Path]:
        return sorted((self.root / "Stories").glob("Story_*.xml"))

    def spreads(self) -> List[Path]:
        return sorted((self.root / "Spreads").glob("Spread_*.xml"))

    def resource(self, name: str) -> Optional[Path]:
        p = self.root / "Resources" / name
        return p if p.exists() else None

    def story_order(self) -> List[str]:
        """Story IDs in the designmap's declared processing order."""
        tree = etree.parse(str(self.designmap))
        doc = tree.getroot()
        story_list = doc.get("StoryList", "")
        return story_list.split()

    def spread_order(self) -> List[str]:
        """Spread part names in designmap order (defines page sequence)."""
        tree = etree.parse(str(self.designmap))
        order: List[str] = []
        for el in tree.iter("{%s}Spread" % IDPKG_NS):
            src = el.get("src", "")
            m = re.search(r"(Spread_[^/]+\.xml)", src)
            if m:
                order.append(m.group(1))
        return order
