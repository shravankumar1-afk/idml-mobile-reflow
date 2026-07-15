"""Adapter: maps raw IDML records into the semantic composite model.

Two responsibilities:
  * classify a paragraph (by style name + content shape) into a BlockType, and
  * turn RawRuns into styled InlineRuns.

Math policy: anchored MathType equations become inline image runs here. Later
the pipeline attaches a LaTeX transcription (from the equation map) to each such
run when one exists, so the renderer emits KaTeX; equations with no transcription
fall back to their original image. Live-text math/chemistry (not MathType) is
rendered as ordinary text with real <sub>/<sup> and the Unicode symbols already
present in the story.
"""
from __future__ import annotations

import re
from typing import List, Optional

from idml2mobile.model.blocks import (
    Block,
    BlockType,
    ImageBlock,
    InlineRun,
    TextBlock,
)
from idml2mobile.parsers.base import Frame, RawParagraph, RawRun

# Style-name keyword -> semantic type. Checked in order; first hit wins.
# Patterns are tuned to THIS source's real paragraph-style names (see style
# census): "NEW:Head-13" is a main heading; "Heading 3"/"2-Sub Hed" are
# sub-headings; "Heading 2" holds the "Key Note" callout label; "Bullets"/
# "Key Bullet" are list items; "Indent"/"i to ii" are indented sub-points.
_STYLE_RULES = [
    (re.compile(r"chapter\s*name", re.I), BlockType.CHAPTER_TITLE),
    # Sub-headings BEFORE the generic heading rule. In this source "Heading 2"
    # and "Heading 3" are the real sub-heading styles (e.g. "Solubility of a
    # solid in liquid", "Normal Boiling Point"); "Head-13" is the main blue
    # heading. "Key Note" also uses Heading 2 but is caught by the callout path
    # in the renderer (it keys off the text, before the sub-heading emit).
    (re.compile(r"heading\s*2|heading\s*3|sub\s*hed|sub\s*head", re.I), BlockType.SUBHEADING),
    (re.compile(r"head-?13|\bhead\b|heading\s*1|head-", re.I), BlockType.HEADING),
    (re.compile(r"key\s*bullet|bullet", re.I), BlockType.LIST_ITEM),
    (re.compile(r"indent|i to ii", re.I), BlockType.SUBPOINT),
    (re.compile(r"figure|caption", re.I), BlockType.CAPTION),
    (re.compile(r"example", re.I), BlockType.EXAMPLE),
    (re.compile(r"que\s*text|question|ques\b", re.I), BlockType.QUESTION),
    (re.compile(r"option|choice", re.I), BlockType.OPTION),
    (re.compile(r"sol\s*text|solution|answer\s*key|answer|explanation", re.I),
     BlockType.SOLUTION),
    (re.compile(r"note|callout|tip|caution|important", re.I), BlockType.NOTE),
]

_OPTION_RE = re.compile(r"^\s*\(?[A-Da-d1-4][\).]\s+")
_QUESTION_RE = re.compile(r"^\s*(Q\.?\s*\d+|Question\s*\d+|\d+\.)\s", re.I)


class IDMLAdapter:
    def paragraph_to_block(self, para: RawParagraph) -> Optional[Block]:
        if not para.text.strip() and not any(r.is_image for r in para.runs):
            return None

        block_type = self._classify(para)
        runs = self._to_inline_runs(para.runs)
        block = TextBlock(block_type, runs=runs)
        self._stamp(block, para)
        return block

    def image_frame_to_block(self, frame: Frame, src: str, original_ref: str) -> ImageBlock:
        block = ImageBlock(src=src, original_ref=original_ref)
        block.page = frame.page_index
        block.column = frame.column
        block.x = frame.x
        block.y = frame.y
        block.frame_id = frame.self_id
        if frame.width:
            block.width = frame.width
        if frame.height:
            block.height = frame.height
        return block

    # -- internals ---------------------------------------------------------
    def _classify(self, para: RawParagraph) -> BlockType:
        style = para.para_style or ""
        for pattern, block_type in _STYLE_RULES:
            if pattern.search(style):
                return block_type

        text = para.text.strip()
        # Fall back to content-shape heuristics.
        if _OPTION_RE.match(text) and len(text) < 200:
            return BlockType.OPTION
        if _QUESTION_RE.match(text):
            return BlockType.QUESTION
        # Big, short, bold line at the top of a story reads as a heading.
        if len(text) < 80 and para.runs and para.runs[0].point_size >= 18:
            return BlockType.HEADING
        return BlockType.PARAGRAPH

    def _to_inline_runs(self, raw_runs: List[RawRun]) -> List[InlineRun]:
        runs: List[InlineRun] = []
        for r in raw_runs:
            if r.is_image:
                runs.append(InlineRun(is_image=True, original_ref=r.image_uri))
                continue
            if not r.text:
                continue
            runs.append(
                InlineRun(
                    text=r.text,
                    bold=r.bold,
                    italic=r.italic,
                    superscript=r.superscript,
                    subscript=r.subscript,
                    char_style=r.char_style,
                )
            )
        return runs

    @staticmethod
    def _stamp(block: Block, para: RawParagraph) -> None:
        block.story_id = para.story_id
