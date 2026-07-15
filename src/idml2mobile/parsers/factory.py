"""ParserFactory — creates the right Parser for a given IDML part.

Selecting by part kind keeps the pipeline decoupled from concrete parser
classes and gives one seam to register future part types (e.g. MasterSpreads).
"""
from __future__ import annotations

from pathlib import Path

from idml2mobile.parsers.base import Parser
from idml2mobile.parsers.resource_parser import ResourceParser
from idml2mobile.parsers.spread_parser import SpreadParser
from idml2mobile.parsers.story_parser import StoryParser


class ParserFactory:
    @staticmethod
    def for_story(path: Path) -> StoryParser:
        return StoryParser(path)

    @staticmethod
    def for_spread(path: Path, page_base_index: int = 0) -> SpreadParser:
        return SpreadParser(path, page_base_index=page_base_index)

    @staticmethod
    def for_resources(fonts_xml: Path = None, styles_xml: Path = None) -> ResourceParser:  # type: ignore[assignment]
        return ResourceParser(fonts_xml=fonts_xml, styles_xml=styles_xml)

    @classmethod
    def create(cls, kind: str, path: Path, **kw) -> Parser:
        kind = kind.lower()
        if kind == "story":
            return cls.for_story(path)
        if kind == "spread":
            return cls.for_spread(path, **kw)
        if kind == "resources":
            return cls.for_resources(**kw)
        raise ValueError(f"Unknown parser kind: {kind}")
