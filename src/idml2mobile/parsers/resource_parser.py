"""Parses Resources/Fonts.xml and Styles.xml for font + style metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from lxml import etree

from idml2mobile.parsers.base import Parser


@dataclass
class ResourceInfo:
    fonts: List[str] = field(default_factory=list)          # font family names used
    paragraph_styles: List[str] = field(default_factory=list)
    character_styles: List[str] = field(default_factory=list)


class ResourceParser(Parser):
    def __init__(self, fonts_xml: Path = None, styles_xml: Path = None) -> None:  # type: ignore[assignment]
        self.fonts_xml = Path(fonts_xml) if fonts_xml else None
        self.styles_xml = Path(styles_xml) if styles_xml else None

    def parse(self) -> ResourceInfo:
        info = ResourceInfo()
        if self.fonts_xml and self.fonts_xml.exists():
            tree = etree.parse(str(self.fonts_xml))
            for fam in tree.iter("FontFamily"):
                name = fam.get("Name")
                if name:
                    info.fonts.append(name)
        if self.styles_xml and self.styles_xml.exists():
            tree = etree.parse(str(self.styles_xml))
            for ps in tree.iter("ParagraphStyle"):
                nm = ps.get("Name")
                if nm:
                    info.paragraph_styles.append(nm.replace("$ID/", ""))
            for cs in tree.iter("CharacterStyle"):
                nm = cs.get("Name")
                if nm:
                    info.character_styles.append(nm.replace("$ID/", ""))
        return info
