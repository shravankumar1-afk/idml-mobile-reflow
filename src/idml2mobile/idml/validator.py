"""Input-folder validation (spec step 1).

Detects the .idml, Links/, Document fonts/, and optional reference .pdf, and
reports missing links and fonts referenced by the package.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote


@dataclass
class ValidationResult:
    input_dir: Path
    idml_file: Optional[Path] = None
    indd_file: Optional[Path] = None
    reference_pdf: Optional[Path] = None
    links_dir: Optional[Path] = None
    fonts_dir: Optional[Path] = None
    missing_links: List[str] = field(default_factory=list)
    present_links: List[str] = field(default_factory=list)
    fonts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.idml_file is not None and not self.errors

    def as_dict(self) -> dict:
        return {
            "input_dir": str(self.input_dir),
            "idml_file": str(self.idml_file) if self.idml_file else None,
            "indd_file": str(self.indd_file) if self.indd_file else None,
            "reference_pdf": str(self.reference_pdf) if self.reference_pdf else None,
            "links_dir": str(self.links_dir) if self.links_dir else None,
            "fonts_dir": str(self.fonts_dir) if self.fonts_dir else None,
            "present_links": self.present_links,
            "missing_links": self.missing_links,
            "fonts": self.fonts,
            "warnings": self.warnings,
            "errors": self.errors,
            "ok": self.ok,
        }


class InputValidator:
    LINK_URI_RE = re.compile(r'LinkResourceURI="([^"]+)"')

    def validate(self, input_path: Path) -> ValidationResult:
        input_path = Path(input_path)
        # Accept either a folder or a direct .idml file.
        if input_path.is_file() and input_path.suffix.lower() == ".idml":
            base = input_path.parent
            result = ValidationResult(input_dir=base, idml_file=input_path)
        else:
            base = input_path
            result = ValidationResult(input_dir=base)
            idmls = sorted(base.glob("*.idml"))
            if not idmls:
                # The package may sit in a subfolder (a common export layout is
                # an outer folder wrapping "<Name> Folder/<Name>.idml"). Search
                # down and anchor on the nearest .idml we find.
                nested = self._find_nested_idml(base)
                if nested:
                    idmls = nested
                    base = idmls[0].parent
                    result.input_dir = base
            if not idmls:
                result.errors.append(
                    "No .idml file found in the selected folder or its subfolders."
                )
            else:
                result.idml_file = idmls[0]
                if len(idmls) > 1:
                    result.warnings.append(
                        f"Multiple .idml files found; using "
                        f"{idmls[0].relative_to(base) if idmls[0].is_relative_to(base) else idmls[0].name}"
                    )

        # Optional siblings
        indd = sorted(base.glob("*.indd"))
        result.indd_file = indd[0] if indd else None
        pdfs = sorted(base.glob("*.pdf"))
        result.reference_pdf = pdfs[0] if pdfs else None

        result.links_dir = self._find_dir(base, "Links")
        result.fonts_dir = self._find_dir(base, ("Document fonts", "Document Fonts"))

        if result.links_dir is None:
            result.warnings.append("No Links/ folder found — images may be missing.")
        if result.fonts_dir is None:
            result.warnings.append("No 'Document fonts' folder found — fonts will fall back.")
        else:
            result.fonts = sorted(
                p.name for p in result.fonts_dir.glob("*")
                if p.suffix.lower() in (".ttf", ".otf", ".ttc")
            )

        if result.idml_file:
            self._check_links(result)
        return result

    @staticmethod
    def _find_nested_idml(base: Path) -> list:
        """Find .idml files in subfolders, preferring the shallowest package."""
        found = sorted(base.rglob("*.idml"), key=lambda p: (len(p.parts), str(p)))
        if not found:
            return []
        package_dir = found[0].parent
        return sorted(p for p in found if p.parent == package_dir)

    @staticmethod
    def _find_dir(base: Path, names) -> Optional[Path]:
        if isinstance(names, str):
            names = (names,)
        for name in names:
            p = base / name
            if p.is_dir():
                return p
        return None

    def _check_links(self, result: ValidationResult) -> None:
        """Read the IDML's referenced link basenames; check they exist in Links/."""
        referenced: List[str] = []
        try:
            with zipfile.ZipFile(result.idml_file) as zf:
                for name in zf.namelist():
                    if name.startswith("Spreads/") and name.endswith(".xml"):
                        text = zf.read(name).decode("utf-8", "ignore")
                        for uri in self.LINK_URI_RE.findall(text):
                            referenced.append(Path(unquote(uri)).name)
        except zipfile.BadZipFile:
            result.errors.append("IDML is not a readable zip archive.")
            return

        referenced = sorted(set(referenced))
        for base_name in referenced:
            found = (
                result.links_dir is not None
                and (result.links_dir / base_name).exists()
            )
            if found:
                result.present_links.append(base_name)
            else:
                result.missing_links.append(base_name)
