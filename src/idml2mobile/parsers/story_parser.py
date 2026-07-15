"""Parses a Stories/Story_*.xml file into a RawStory.

Handles the IDML nesting:
  Story > ParagraphStyleRange > CharacterStyleRange > Content | Br
Bold/italic come from FontStyle + AppliedFont; super/subscript from Position.
"""
from __future__ import annotations

import re
from typing import Optional

from lxml import etree

from idml2mobile.parsers.base import Parser, RawParagraph, RawRun, RawStory


class StoryParser(Parser):
    _GRAPHIC_TAGS = {
        "Rectangle", "Polygon", "Oval", "GraphicLine", "Group",
        "Image", "EPS", "WMF", "PDF", "ImportedPage",
    }

    def parse(self) -> Optional[RawStory]:
        tree = etree.parse(str(self.path))
        story_el = tree.find(".//Story")
        if story_el is None:
            return None
        story_id = story_el.get("Self", self.path.stem)
        raw = RawStory(story_id=story_id)

        for psr in story_el.findall("ParagraphStyleRange"):
            para = RawParagraph(
                para_style=self._short_style(psr.get("AppliedParagraphStyle", "")),
                story_id=story_id,
            )
            for csr in psr.findall("CharacterStyleRange"):
                self._collect_runs(csr, para)
            if para.runs:
                raw.paragraphs.append(para)
                raw.image_refs.extend(r.image_uri for r in para.runs if r.image_uri)
        return raw

    def _collect_runs(self, csr: etree._Element, para: RawParagraph) -> None:
        font_style = (csr.get("FontStyle") or "").lower()
        position = (csr.get("Position") or "")
        char_style = self._short_style(csr.get("AppliedCharacterStyle", ""))
        point_size = float(csr.get("PointSize") or 0)
        font = ""
        applied_font = csr.find(".//AppliedFont")
        if applied_font is not None and applied_font.text:
            font = applied_font.text

        bold = "bold" in font_style or "black" in font_style or "semibold" in font_style
        italic = "italic" in font_style or "oblique" in font_style
        superscript = "superscript" in position.lower()
        subscript = "subscript" in position.lower()

        # Walk direct children in document order: Content text, <Br/> breaks,
        # and anchored graphics (Rectangle/Polygon/Image/... containing a Link).
        for node in csr:
            tag = etree.QName(node).localname
            if tag == "Content" and node.text:
                text = self._normalize(self._symbol_text(node.text, font))
                if text:
                    para.runs.append(
                        RawRun(
                            text=text,
                            bold=bold,
                            italic=italic,
                            superscript=superscript,
                            subscript=subscript,
                            char_style=char_style,
                            font=font,
                            point_size=point_size,
                        )
                    )
            elif tag == "Br":
                if para.runs:
                    para.runs.append(RawRun(text="\n"))
            elif tag == "Table":
                grid = self._parse_table(node)
                if grid:
                    para.runs.append(RawRun(text="", table=grid))
            elif tag in self._GRAPHIC_TAGS or tag == "TextFrame":
                # Anchored TEXT frames (Key Notes / callout boxes) reference their
                # own story; capture those as box refs. Otherwise it's an anchored
                # graphic (image/equation) referenced by a Link.
                frames = list(node.iter("TextFrame"))
                if tag == "TextFrame":
                    frames = [node] + frames
                box_ids = []
                for tf in frames:
                    ps = tf.get("ParentStory")
                    if ps and ps not in box_ids:
                        box_ids.append(ps)
                if box_ids:
                    for bid in box_ids:
                        para.runs.append(RawRun(text="", textframe_story=bid))
                else:
                    link = node.find(".//Link")
                    uri = link.get("LinkResourceURI") if link is not None else None
                    if uri:
                        para.runs.append(RawRun(text="", image_uri=uri))

    def _parse_table(self, tbl) -> list:
        """Parse an IDML <Table> into normalized rows of cell dicts, honouring
        row/column spans. Cell names are 'col:row' (0-indexed)."""
        try:
            ncols = int(tbl.get("ColumnCount") or 0)
        except ValueError:
            ncols = 0
        cellmap = {}
        maxrow = maxcol = 0
        for c in tbl.findall("Cell"):
            nm = c.get("Name", "")
            if ":" not in nm:
                continue
            try:
                col, row = (int(v) for v in nm.split(":")[:2])
            except ValueError:
                continue
            rs = int(float(c.get("RowSpan") or 1))
            cs = int(float(c.get("ColumnSpan") or 1))
            text, cell_html = self._cell_content(c)
            cellmap[(row, col)] = (rs, cs, text, cell_html)
            maxrow = max(maxrow, row + rs - 1)
            maxcol = max(maxcol, col + cs - 1)
        if not cellmap:
            return []
        nrows = maxrow + 1
        ncols = max(ncols, maxcol + 1)
        occ = [[False] * ncols for _ in range(nrows)]
        rows = []
        for r in range(nrows):
            row_cells = []
            for c in range(ncols):
                if occ[r][c]:
                    continue
                if (r, c) in cellmap:
                    rs, cs, text, cell_html = cellmap[(r, c)]
                    row_cells.append({"text": text, "html": cell_html,
                                      "colspan": cs, "rowspan": rs})
                    for rr in range(r, min(nrows, r + rs)):
                        for cc in range(c, min(ncols, c + cs)):
                            occ[rr][cc] = True
                else:
                    row_cells.append({"text": "", "colspan": 1, "rowspan": 1})
                    occ[r][c] = True
            if row_cells:
                rows.append(row_cells)
        return rows

    def _cell_content(self, cell) -> tuple:
        """Return (plain_text, html) for a table cell, preserving sub/superscripts
        (e.g. CO2 -> CO<sub>2</sub>) and bold so chemistry renders correctly."""
        from xml.sax.saxutils import escape
        plain_parts, html_parts = [], []
        for csr in cell.iter("CharacterStyleRange"):
            position = (csr.get("Position") or "").lower()
            fs = (csr.get("FontStyle") or "").lower()
            sub = "subscript" in position
            sup = "superscript" in position
            bold = "bold" in fs or "black" in fs or "semibold" in fs
            for ct in csr.iter("Content"):
                raw = ct.text or ""
                if not raw:
                    continue
                norm = self._normalize(raw).replace("\n", " ")
                plain_parts.append(norm)
                piece = escape(norm)
                if sub:
                    piece = f"<sub>{piece}</sub>"
                elif sup:
                    piece = f"<sup>{piece}</sup>"
                if bold:
                    piece = f"<strong>{piece}</strong>"
                html_parts.append(piece)
        plain = re.sub(r"\s{2,}", " ", "".join(plain_parts)).strip()
        html = re.sub(r"\s{2,}", " ", "".join(html_parts)).strip()
        return plain, html

    @staticmethod
    def _symbol_text(text: str, font: str) -> str:
        """Normalize legacy symbol-font private glyphs to portable Unicode."""
        if not text:
            return text
        if font.lower() in {"mt extra", "mt extra tiger"}:
            table = {
                "": "l",       # liquid-state marker in H2O(l)
                "": "⇌",       # equilibrium arrow
                "": "C",       # concentration symbol
            }
            return "".join(table.get(ch, ch) for ch in text)
        if font.lower() == "symbol":
            return text.replace("", "")
        return text

    @staticmethod
    def _normalize(text: str) -> str:
        # Repair UTF-8 bytes stored/read as Windows-1252 by legacy workflows.
        if any(mark in text for mark in ("?", "?", "?")):
            try:
                text = text.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        text = text.replace("\u2029", "\n").replace("\u2028", "\n")
        text = text.replace("???", "\n").replace("???", "\n")
        text = text.replace("\t", " ")
        return re.sub(r"[ ]{2,}", " ", text)

    @staticmethod
    def _short_style(applied: str) -> str:
        # "ParagraphStyle/Heading 1" -> "Heading 1"; strip "$ID/" prefixes.
        name = applied.split("/")[-1]
        return name.replace("$ID/", "").strip()

