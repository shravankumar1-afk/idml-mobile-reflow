"""Parser abstractions and the raw (pre-semantic) data structures.

Parsers turn IDML XML into these neutral records. The Adapter later maps them
into the semantic composite model. Keeping raw records separate means the
messy XML details never leak past the parser layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class RawRun:
    text: str
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False
    char_style: str = ""
    font: str = ""
    point_size: float = 0.0
    image_uri: str = ""         # set when this run is an inline anchored graphic
    textframe_story: str = ""   # set when this run is an anchored text frame (a box)
    table: object = None        # set when this run is a table: list[list[dict]]

    @property
    def is_image(self) -> bool:
        return bool(self.image_uri)

    @property
    def is_textframe(self) -> bool:
        return bool(self.textframe_story)


@dataclass
class RawParagraph:
    runs: List[RawRun] = field(default_factory=list)
    para_style: str = ""
    story_id: str = ""

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class RawStory:
    story_id: str
    paragraphs: List[RawParagraph] = field(default_factory=list)
    # image references embedded directly in the story (inline anchored art)
    image_refs: List[str] = field(default_factory=list)


@dataclass
class Frame:
    """A text or image frame placed on a page."""

    self_id: str
    kind: str                       # "text" | "image"
    story_id: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    page_index: int = 0
    page_name: str = ""
    column_count: int = 1
    prev_frame: str = ""            # threading
    next_frame: str = ""
    link_uri: str = ""              # for image frames
    column: int = 0                 # 0 = left, 1 = right (filled by geometry)


@dataclass
class PageInfo:
    self_id: str
    name: str
    index: int
    width: float
    height: float
    x_offset: float = 0.0
    y_offset: float = 0.0


class Parser(ABC):
    """Abstract parser over a single IDML part file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @abstractmethod
    def parse(self):  # noqa: ANN201 - return type varies per concrete parser
        ...
