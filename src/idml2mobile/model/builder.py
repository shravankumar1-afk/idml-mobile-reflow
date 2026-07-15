"""DocumentBuilder — assembles an ordered list of blocks into the composite tree.

Builder pattern: callers push blocks in final reading order; the builder groups
them under Sections (opened by chapter_title / heading blocks) and returns a
finished `Document`. This keeps section-grouping logic in one place instead of
scattered through the parsers.
"""
from __future__ import annotations

from typing import List, Optional

from idml2mobile.model.blocks import Block, BlockType, Document, Section


class DocumentBuilder:
    def __init__(self, title: str = "") -> None:
        self._doc = Document(title=title)
        self._current: Optional[Section] = None

    def set_title(self, title: str) -> "DocumentBuilder":
        self._doc.title = title
        return self

    def set_meta(self, **meta) -> "DocumentBuilder":
        self._doc.meta.update(meta)
        return self

    def _ensure_section(self) -> Section:
        if self._current is None:
            self._current = Section(title="", level=1)
            self._doc.add(self._current)
        return self._current

    def add_block(self, block: Block) -> "DocumentBuilder":
        if block.type in (BlockType.CHAPTER_TITLE, BlockType.HEADING):
            level = 1 if block.type == BlockType.CHAPTER_TITLE else 2
            title = getattr(block, "text", "")
            self._current = Section(title=title, level=level)
            self._doc.add(self._current)
            self._current.add(block)
        else:
            self._ensure_section().add(block)
        return self

    def add_blocks(self, blocks: List[Block]) -> "DocumentBuilder":
        for block in blocks:
            self.add_block(block)
        return self

    def build(self) -> Document:
        # Drop fully-empty sections that can leave blank PDF pages.
        self._doc.children = [
            s for s in self._doc.children
            if s.children or s.title.strip()
        ]
        return self._doc
