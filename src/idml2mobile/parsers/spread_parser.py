"""Parses a Spreads/Spread_*.xml file into pages + placed frames.

Computes absolute (spread-space) geometry by applying each item's ItemTransform
to its GeometricBounds, so text/image frames can later be assigned to a page,
a column, and a top-to-bottom order.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from lxml import etree

from idml2mobile.parsers.base import Frame, Parser, PageInfo


def _parse_transform(s: str) -> Tuple[float, float, float, float, float, float]:
    parts = [float(x) for x in (s or "1 0 0 1 0 0").split()]
    if len(parts) != 6:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return tuple(parts)  # type: ignore[return-value]


def _apply(t, lx: float, ly: float) -> Tuple[float, float]:
    a, b, c, d, tx, ty = t
    return (a * lx + c * ly + tx, b * lx + d * ly + ty)


def _bounds(el) -> Tuple[float, float, float, float]:
    # GeometricBounds = "y1 x1 y2 x2"
    gb = el.get("GeometricBounds")
    if not gb:
        return (0.0, 0.0, 0.0, 0.0)
    y1, x1, y2, x2 = (float(v) for v in gb.split())
    return (x1, y1, x2, y2)


def _abs_rect(el) -> Tuple[float, float, float, float]:
    """Absolute (x_min, y_min, x_max, y_max) in spread space."""
    x1, y1, x2, y2 = _bounds(el)
    t = _parse_transform(el.get("ItemTransform"))
    corners = [_apply(t, x1, y1), _apply(t, x2, y2), _apply(t, x1, y2), _apply(t, x2, y1)]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return (min(xs), min(ys), max(xs), max(ys))


class SpreadParser(Parser):
    def __init__(self, path: Path, page_base_index: int = 0) -> None:
        super().__init__(path)
        self.page_base_index = page_base_index

    def parse(self) -> Tuple[List[PageInfo], List[Frame]]:
        tree = etree.parse(str(self.path))
        spread_el = tree.find(".//Spread")
        pages: List[PageInfo] = []
        frames: List[Frame] = []
        if spread_el is None:
            return pages, frames

        page_rects: List[Tuple[PageInfo, Tuple[float, float, float, float]]] = []
        for i, page_el in enumerate(spread_el.findall("Page")):
            rect = _abs_rect(page_el)
            info = PageInfo(
                self_id=page_el.get("Self", ""),
                name=page_el.get("Name", str(self.page_base_index + i + 1)),
                index=self.page_base_index + i,
                width=rect[2] - rect[0],
                height=rect[3] - rect[1],
                x_offset=rect[0],
                y_offset=rect[1],
            )
            pages.append(info)
            page_rects.append((info, rect))

        for tf in spread_el.findall(".//TextFrame"):
            frames.append(self._frame_from_element(tf, kind="text", page_rects=page_rects))

        # Image frames: Rectangle/Polygon/Oval containing an Image/EPS/PDF link.
        for shape_tag in ("Rectangle", "Polygon", "Oval", "GraphicLine"):
            for shape in spread_el.findall(".//%s" % shape_tag):
                link = shape.find(".//Link")
                if link is None:
                    continue
                uri = link.get("LinkResourceURI", "")
                if not uri:
                    continue
                frame = self._frame_from_element(shape, kind="image", page_rects=page_rects)
                frame.link_uri = uri
                frames.append(frame)

        return pages, frames

    def _frame_from_element(self, el, kind: str, page_rects) -> Frame:
        rect = _abs_rect(el)
        cx = (rect[0] + rect[2]) / 2
        cy = (rect[1] + rect[3]) / 2
        page = self._assign_page(cx, cy, page_rects)

        col_count = 1
        pref = el.find(".//TextFramePreference")
        if pref is not None:
            col_count = int(float(pref.get("TextColumnCount", "1") or 1))

        column = 0
        if page is not None:
            page_mid_x = page.x_offset + page.width / 2
            column = 1 if cx >= page_mid_x else 0

        return Frame(
            self_id=el.get("Self", ""),
            kind=kind,
            story_id=el.get("ParentStory", ""),
            x=rect[0],
            y=rect[1],
            width=rect[2] - rect[0],
            height=rect[3] - rect[1],
            page_index=page.index if page else self.page_base_index,
            page_name=page.name if page else "",
            column_count=col_count,
            prev_frame=el.get("PreviousTextFrame", "") or "",
            next_frame=el.get("NextTextFrame", "") or "",
            column=column,
        )

    @staticmethod
    def _assign_page(cx: float, cy: float, page_rects):
        best = None
        best_dist = float("inf")
        for info, rect in page_rects:
            if rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
                return info
            mx = (rect[0] + rect[2]) / 2
            my = (rect[1] + rect[3]) / 2
            dist = (cx - mx) ** 2 + (cy - my) ** 2
            if dist < best_dist:
                best_dist, best = dist, info
        return best
