"""Composite content model: Document > Section > Block.

This is the renderer-agnostic representation (the "content" side of the Bridge).
Every node exposes `walk()` so cleanup passes and renderers can traverse the
tree uniformly. Concrete leaves carry the payload (text runs, image, math, table).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional


class BlockType(str, Enum):
    CHAPTER_TITLE = "chapter_title"
    HEADING = "heading"
    SUBHEADING = "subheading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    SUBPOINT = "subpoint"
    CAPTION = "caption"
    EXAMPLE = "example"
    QUESTION = "question"
    OPTION = "option"
    SOLUTION = "solution"
    MATH_DISPLAY = "math_display"
    IMAGE = "image"
    TABLE = "table"
    NOTE = "note"


class Node:
    """Base of the composite tree."""

    def __init__(self) -> None:
        self.children: List["Node"] = []

    def add(self, node: "Node") -> "Node":
        self.children.append(node)
        return node

    def walk(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.walk()


class Document(Node):
    def __init__(self, title: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.title = title
        self.meta: Dict[str, Any] = meta or {}

    @property
    def sections(self) -> List["Section"]:
        return [c for c in self.children if isinstance(c, Section)]


class Section(Node):
    def __init__(self, title: str = "", level: int = 1) -> None:
        super().__init__()
        self.title = title
        self.level = level


@dataclass
class InlineRun:
    """A styled span of text (or an inline anchored image) within a block."""

    text: str = ""
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False
    char_style: str = ""
    # inline anchored graphic (e.g. a MathType WMF equation) placed mid-text:
    is_image: bool = False
    src: str = ""            # resolved web-safe path (filled by the pipeline)
    original_ref: str = ""   # original link URI, for QA
    alt: str = ""
    tall: bool = False       # multi-line equation (e.g. a fraction) -> render larger
    max_h_px: float = 0.0    # physical display height in CSS px (keeps eqn size consistent)
    # LaTeX transcription of an anchored MathType equation (filled by the pipeline
    # from the equation map). When present the renderer emits KaTeX instead of the
    # image; if absent, the original equation image is used as a fallback.
    latex: str = ""


class Block(Node):
    """Base for leaf content blocks. Carries provenance for QA/reading order."""

    def __init__(self, block_type: BlockType) -> None:
        super().__init__()
        self.type = block_type
        # provenance used by reading-order strategies + QA:
        self.page: int = 0
        self.column: int = 0
        self.x: float = 0.0
        self.y: float = 0.0
        self.story_id: str = ""
        self.frame_id: str = ""
        self.order_key: int = 0
        self.box_group: int = 0     # >0 => this block belongs to a box group
        self.box_kind: str = ""     # "callout" (Key Note) | "example" (Ex-N)
        self.anchored: bool = False  # came from an anchored text frame (callout/box)
        self.ex_label: bool = False  # this block is an "Ex-N" ribbon label


class TextBlock(Block):
    def __init__(self, block_type: BlockType, runs: Optional[List[InlineRun]] = None) -> None:
        super().__init__(block_type)
        self.runs: List[InlineRun] = runs or []

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs if not r.is_image)

    @property
    def has_image(self) -> bool:
        return any(r.is_image for r in self.runs)

    def is_empty(self) -> bool:
        return not self.text.strip() and not self.has_image


class ImageBlock(Block):
    def __init__(self, src: str, original_ref: str = "", alt: str = "") -> None:
        super().__init__(BlockType.IMAGE)
        self.src = src                     # web-safe path relative to output
        self.original_ref = original_ref   # original link (eps/wmf/...) for QA
        self.alt = alt
        self.width: Optional[float] = None
        self.height: Optional[float] = None


class MathBlock(Block):
    def __init__(self, latex: str, display: bool = True, fallback_image: str = "") -> None:
        super().__init__(BlockType.MATH_DISPLAY)
        self.latex = latex
        self.display = display
        self.fallback_image = fallback_image   # used if latex could not be built safely


class TableBlock(Block):
    def __init__(self, rows: Optional[List] = None) -> None:
        super().__init__(BlockType.TABLE)
        # rows: list of rows; each row is a list of cell dicts
        # {"text": str, "colspan": int, "rowspan": int}
        self.rows: List[List[dict]] = rows or []
        self.render_mode: str = "scroll"       # stacked | scroll | scaled
