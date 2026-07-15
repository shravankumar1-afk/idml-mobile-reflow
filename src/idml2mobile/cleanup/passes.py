"""Chain of Responsibility for post-extraction cleanup.

Each pass takes the ordered block list, does one focused transformation, and
hands the result to the next link. The chain runs before the DocumentBuilder,
so sections are grouped from already-clean blocks.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List, Optional

from idml2mobile.model.blocks import Block, BlockType, InlineRun, TextBlock


class CleanupPass(ABC):
    def __init__(self) -> None:
        self._next: Optional[CleanupPass] = None

    def set_next(self, nxt: "CleanupPass") -> "CleanupPass":
        self._next = nxt
        return nxt

    def handle(self, blocks: List[Block]) -> List[Block]:
        blocks = self.process(blocks)
        if self._next is not None:
            return self._next.handle(blocks)
        return blocks

    @abstractmethod
    def process(self, blocks: List[Block]) -> List[Block]:
        ...


class NormalizeWhitespace(CleanupPass):
    def process(self, blocks: List[Block]) -> List[Block]:
        for b in blocks:
            if isinstance(b, TextBlock):
                for run in b.runs:
                    run.text = re.sub(r"[ \t]+", " ", run.text.replace("\u2028", " ").replace("\u2029", " "))
                # trim leading/trailing whitespace-only runs
                while b.runs and not b.runs[0].is_image and not b.runs[0].text.strip():
                    b.runs.pop(0)
                while b.runs and not b.runs[-1].is_image and not b.runs[-1].text.strip():
                    b.runs.pop()
        return blocks


class DropEmptyBlocks(CleanupPass):
    def process(self, blocks: List[Block]) -> List[Block]:
        out: List[Block] = []
        for b in blocks:
            if isinstance(b, TextBlock) and b.is_empty():
                continue
            out.append(b)
        return out


class MergeBrokenParagraphs(CleanupPass):
    """Join consecutive PARAGRAPH blocks from the same story where the first
    ends mid-sentence (no terminal punctuation) — repairs frame-split text."""

    _ENDS = (".", "!", "?", ":", ";", "”", '"', ")")

    def process(self, blocks: List[Block]) -> List[Block]:
        out: List[Block] = []
        for b in blocks:
            if (
                out
                and isinstance(b, TextBlock)
                and isinstance(out[-1], TextBlock)
                and b.type == BlockType.PARAGRAPH
                and out[-1].type == BlockType.PARAGRAPH
                and out[-1].story_id == b.story_id
                and out[-1].text.strip()
                and not out[-1].text.rstrip().endswith(self._ENDS)
            ):
                prev = out[-1]
                if prev.runs and prev.runs[-1].text and not prev.runs[-1].text.endswith(" "):
                    prev.runs.append(InlineRun(text=" "))
                prev.runs.extend(b.runs)
            else:
                out.append(b)
        return out


class CollapseDuplicateHeadings(CleanupPass):
    """Remove a heading immediately repeated (common with running headers)."""

    def process(self, blocks: List[Block]) -> List[Block]:
        out: List[Block] = []
        for b in blocks:
            if (
                out
                and isinstance(b, TextBlock)
                and isinstance(out[-1], TextBlock)
                and b.type in (BlockType.HEADING, BlockType.CHAPTER_TITLE)
                and out[-1].type == b.type
                and out[-1].text.strip() == b.text.strip()
            ):
                continue
            out.append(b)
        return out


def default_chain() -> CleanupPass:
    """Wire the standard cleanup chain and return its head."""
    head = NormalizeWhitespace()
    head.set_next(MergeBrokenParagraphs()).set_next(DropEmptyBlocks()).set_next(
        CollapseDuplicateHeadings()
    )
    return head


class CleanupChain:
    """Thin convenience wrapper around a head pass."""

    def __init__(self, head: Optional[CleanupPass] = None) -> None:
        self.head = head or default_chain()

    def run(self, blocks: List[Block]) -> List[Block]:
        return self.head.handle(blocks)
