"""Strategy pattern for reconstructing reading order from placed frames.

Each strategy consumes the flat list of frames parsed from the spreads and
returns an ordered list of `FrameGroup`s (a story to expand, or an image to
place). The pipeline then expands each story into its blocks, so a story split
across several threaded frames is emitted once, in the right place.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List

from idml2mobile.parsers.base import Frame


@dataclass
class FrameGroup:
    kind: str            # "story" | "image"
    page_index: int
    column: int
    y: float
    x: float
    story_id: str = ""
    frame: Frame = None  # type: ignore[assignment]


def _pos_key(g: FrameGroup):
    # page, then column (left col before right), then top-to-bottom, then left.
    return (g.page_index, g.column, round(g.y, 1), round(g.x, 1))


class ReadingOrderStrategy(ABC):
    name = "base"

    @abstractmethod
    def order(self, frames: List[Frame]) -> List[FrameGroup]:
        ...


class GeometricColumnStrategy(ReadingOrderStrategy):
    """Sort by page → left column → right column → top-to-bottom."""

    name = "geometric"

    def order(self, frames: List[Frame]) -> List[FrameGroup]:
        groups: List[FrameGroup] = []
        seen_story: set = set()
        text_frames = sorted(
            (f for f in frames if f.kind == "text" and f.story_id),
            key=lambda f: (f.page_index, f.column, f.y, f.x),
        )
        for f in text_frames:
            if f.story_id in seen_story:
                continue
            seen_story.add(f.story_id)
            groups.append(
                FrameGroup("story", f.page_index, f.column, f.y, f.x, f.story_id, f)
            )
        for f in frames:
            if f.kind == "image":
                groups.append(
                    FrameGroup("image", f.page_index, f.column, f.y, f.x, "", f)
                )
        groups.sort(key=_pos_key)
        return groups


class ThreadedOrderStrategy(ReadingOrderStrategy):
    """Follow PreviousTextFrame/NextTextFrame chains; place story at chain start."""

    name = "threaded"

    def order(self, frames: List[Frame]) -> List[FrameGroup]:
        by_id: Dict[str, Frame] = {f.self_id: f for f in frames if f.self_id}
        groups: List[FrameGroup] = []
        seen_story: set = set()

        starts = [
            f for f in frames
            if f.kind == "text" and f.story_id and (not f.prev_frame or f.prev_frame not in by_id)
        ]
        starts.sort(key=lambda f: (f.page_index, f.column, f.y, f.x))
        for f in starts:
            if f.story_id in seen_story:
                continue
            seen_story.add(f.story_id)
            groups.append(
                FrameGroup("story", f.page_index, f.column, f.y, f.x, f.story_id, f)
            )

        # any text frame whose story wasn't captured via a start frame
        for f in sorted(frames, key=lambda f: (f.page_index, f.column, f.y, f.x)):
            if f.kind == "text" and f.story_id and f.story_id not in seen_story:
                seen_story.add(f.story_id)
                groups.append(
                    FrameGroup("story", f.page_index, f.column, f.y, f.x, f.story_id, f)
                )
            elif f.kind == "image":
                groups.append(
                    FrameGroup("image", f.page_index, f.column, f.y, f.x, "", f)
                )
        groups.sort(key=_pos_key)
        return groups


class StoryOrderStrategy(ReadingOrderStrategy):
    """Trust the designmap StoryList order (fallback / debugging aid)."""

    name = "story_order"

    def __init__(self, story_order: List[str]) -> None:
        self.story_order = story_order

    def order(self, frames: List[Frame]) -> List[FrameGroup]:
        rank = {sid: i for i, sid in enumerate(self.story_order)}
        groups: List[FrameGroup] = []
        seen: set = set()
        for f in frames:
            if f.kind == "text" and f.story_id and f.story_id not in seen:
                seen.add(f.story_id)
                groups.append(
                    FrameGroup("story", f.page_index, f.column, f.y, f.x, f.story_id, f)
                )
            elif f.kind == "image":
                groups.append(
                    FrameGroup("image", f.page_index, f.column, f.y, f.x, "", f)
                )
        groups.sort(key=lambda g: rank.get(g.story_id, 10_000) if g.kind == "story" else 10_001)
        return groups


class AutoStrategy(ReadingOrderStrategy):
    """Use threading when the document is threaded, else geometry."""

    name = "auto"

    def order(self, frames: List[Frame]) -> List[FrameGroup]:
        threaded = any(f.next_frame or f.prev_frame for f in frames if f.kind == "text")
        chosen = ThreadedOrderStrategy() if threaded else GeometricColumnStrategy()
        return chosen.order(frames)


def get_strategy(name: str, story_order: List[str] = None) -> ReadingOrderStrategy:  # type: ignore[assignment]
    name = (name or "auto").lower()
    if name == "threaded":
        return ThreadedOrderStrategy()
    if name == "geometric":
        return GeometricColumnStrategy()
    if name == "story_order":
        return StoryOrderStrategy(story_order or [])
    return AutoStrategy()
