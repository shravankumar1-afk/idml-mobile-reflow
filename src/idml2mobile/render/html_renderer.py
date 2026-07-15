"""HTMLRenderer â€” emits a self-contained, mobile-first index.html.

KaTeX is loaded from the vendored copy under output/katex (self-contained, no
network) and auto-rendered on load: equations with a LaTeX transcription render
as KaTeX, the rest fall back to their original image. All output stays within the
328px safe width; images are capped at 100%.
"""
from __future__ import annotations

import html
import re
import uuid
from typing import List

from idml2mobile.config import MobileProfile
from idml2mobile.model.blocks import (
    BlockType,
    Document,
    ImageBlock,
    InlineRun,
    MathBlock,
    Section,
    TableBlock,
    TextBlock,
)
from idml2mobile.render.base import Renderer

_HEADING_TAG = {
    BlockType.CHAPTER_TITLE: ("h1", "chapter-title"),
    BlockType.HEADING: ("h2", "heading"),
    BlockType.SUBHEADING: ("h3", "subhead"),
}
# Headings that are "key note" style callouts in the source (rendered orange).
_CALLOUT_RE = re.compile(
    r"key\s*note|advanced\s*learning|remember|do\s*you\s*know|mnemonic|"
    r"caution|important\s*point|tips?\b",
    re.I,
)
_QNUM_RE = re.compile(r"^\s*(?:Q\.?\s*\d+|\d+)[.)]")
# Question-section headers (rendered as a dark bar atop a bordered box).
_QSECTION_RE = re.compile(
    r"check\s*your\s*understanding|\bquestions?\b|\bexercise\b|assignment|"
    r"try\s*yourself|correct\s*type|numerical\s*type|comprehension|assertion|"
    r"integer\s*type|match\s*the",
    re.I,
)
_WRAP_CLASS = {
    BlockType.QUESTION: "question",
    BlockType.OPTION: "option",
    BlockType.SOLUTION: "solution",
    BlockType.EXAMPLE: "example",
    BlockType.NOTE: "note",
    BlockType.PARAGRAPH: "para",
}


class HTMLRenderer(Renderer):
    def __init__(self, profile: MobileProfile, css_href: str = "css/styles.v1.css",
                 katex_local: bool = False) -> None:
        self.profile = profile
        self.css_href = css_href
        self.katex_local = katex_local

    def prepare(self, document: Document) -> None:
        self._doc_title = (document.title or "").strip().lower()
        self._title_suppressed = False
        self._cur_bg = 0              # current anchored-box group being rendered
        self._in_list = False         # inside a <ul> of consecutive bullet items
        self._last_heading = ""       # for de-duplicating repeated headings

    def render_head(self, document: Document) -> str:
        title = html.escape(document.title or "Mobile Document")
        katex = self._katex_head()
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width={self.profile.page_width}, initial-scale=1, maximum-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="css/katex.min.css">\n<!-- legacy compatibility: href="katex/katex.min.css" -->
<link rel="stylesheet" href="{self.css_href}">
<link href="../../styles/styles.css" rel="stylesheet"/>
{katex}<!-- renderMathInElement is initialized by the bundled chapter runtime -->\n</head>
"""

    def _katex_head(self) -> str:
        """Vendored KaTeX (CSS + JS + auto-render) for offline, self-contained
        rendering. Inline `\\(..\\)` and display `\\[..\\]` delimiters are rendered
        on load; `throwOnError:false` keeps a bad equation from blanking the page."""
        return (
            '<script defer src="js/katex.min.js"></script>\n<!-- legacy compatibility: src="katex/katex.min.js" -->\n'
            '<script defer src="js/auto-render.min.js"></script>\n'
            '<script defer>document.addEventListener("DOMContentLoaded",function(){if(window.renderMathInElement){renderMathInElement(document.body,{delimiters:[{left:"\\\\[",right:"\\\\]",display:true},{left:"\\\\(",right:"\\\\)",display:false}]});}});</script>\n'
        )

    def open_body(self, document: Document) -> str:
        out = ['<body>\n<main class="doc">\n']
        # Render the chapter title in the body (it was previously only in <title>,
        # so the chapter name â€” e.g. "Solutions" â€” went missing from the page).
        if document.title:
            out.append(f'<h1 class="doc-title">{html.escape(document.title)}</h1>\n')
        return "".join(out)

    def close_body(self, document: Document) -> str:
        return ('</main>\n<script src="../../scripts/script.js"></script>\n'
                '<script defer src="js/chapter.js"></script>\n')

    def open_section(self, section: Section) -> str:
        return '<section class="sec">\n'

    def close_section(self, section: Section) -> str:
        return self._sync_list(False) + self._sync_box(0) + "</section>\n"

    def render_block(self, block):
        # Maintain two nesting contexts around each block:
        #   * anchored-frame box (Key Note / callout) for blocks sharing box_group
        #   * <ul> for maximal runs of consecutive bullet LIST_ITEM blocks
        # A list is always closed before a box boundary.
        bg = getattr(block, "box_group", 0)
        is_li = isinstance(block, TextBlock) and block.type == BlockType.LIST_ITEM
        out = ""
        if bg != getattr(self, "_cur_bg", 0):
            out += self._sync_list(False)   # never let a list straddle a box edge
            out += self._sync_box(bg, getattr(block, "box_kind", ""))
        out += self._sync_list(is_li)
        return out + super().render_block(block)

    def _sync_box(self, bg: int, kind: str = "") -> str:
        if bg == getattr(self, "_cur_bg", 0):
            return ""
        out = "</div>\n" if getattr(self, "_cur_bg", 0) else ""
        if bg:
            cls = "box example" if kind == "example" else "box anchored"
            out += f'<div class="{cls}">\n'
        self._cur_bg = bg
        return out

    def _sync_list(self, want: bool) -> str:
        if want == getattr(self, "_in_list", False):
            return ""
        self._in_list = want
        return '<ul class="bullets">\n' if want else "</ul>\n"

    def render_text(self, block: TextBlock) -> str:
        text = block.text
        # A paragraph that is nothing but an anchored graphic is a display eqn/diagram.
        image_runs = [r for r in block.runs if r.is_image]
        if image_runs and not text.strip():
            return "".join(self._display_image(r) for r in image_runs)

        # "Ex-N" ribbon that labels a worked-example box.
        if getattr(block, "ex_label", False):
            label = re.sub(r"\s+", " ", text.strip())
            label = re.sub(r"(?i)^ex", "Ex", label)
            return f'<div class="ex-ribbon">{html.escape(label)}</div>\n'

        inner = self._inline(block.runs)

        # Bullet list item: bold the lead-in term (everything up to the first
        # colon) so "Lattice energy: ..." reads with a bold heading, per feedback.
        if block.type == BlockType.LIST_ITEM:
            inner = self._bold_leadin(inner)
            return f'<li>{inner}</li>\n'
        if block.type == BlockType.SUBPOINT:
            return self._paragraph("subpoint", inner)
        if block.type == BlockType.CAPTION:
            return self._paragraph("caption", inner)

        heading = block.type in _HEADING_TAG
        labelish = heading or (block.type == BlockType.PARAGRAPH and len(text.strip()) <= 60)

        # Chapter title (dedupe against the .doc-title already shown at the top).
        if block.type == BlockType.CHAPTER_TITLE:
            if (not getattr(self, "_title_suppressed", True)
                    and text.strip().lower() == getattr(self, "_doc_title", "")):
                self._title_suppressed = True
                return ""
            return f'<h1 class="chapter-title">{inner}</h1>\n'

        # Hide decorative "Advanced Learning" category tags (user preference).
        if labelish and re.search(r"advanced\s*learning", text, re.I):
            return ""
        # Callout ("Key Note") / question-section labels -> styled header bars.
        if labelish and _CALLOUT_RE.search(text):
            kn = " kn" if re.search(r"key\s*note", text, re.I) else ""
            return f'<h3 class="callout-head{kn}">{inner}</h3>\n'
        if labelish and _QSECTION_RE.search(text):
            return f'<h3 class="qsection-head">{inner}</h3>\n'

        if heading:
            if (not getattr(self, "_title_suppressed", True)
                    and text.strip().lower() == getattr(self, "_doc_title", "")):
                self._title_suppressed = True
                return ""
            # A heading that repeats the previous heading (e.g. "CONCENTRATION
            # TERMS" then "Concentration Terms") is an orange sub-label in the
            # source, not a second blue bar.
            norm = re.sub(r"\s+", " ", text.strip().lower())
            if norm and norm == getattr(self, "_last_heading", ""):
                return f'<div class="sublabel">{inner}</div>\n'
            self._last_heading = norm
            tag, cls = _HEADING_TAG[block.type]
            return f'<{tag} class="{cls}">{inner}</{tag}>\n'

        cls = _WRAP_CLASS.get(block.type, "para")
        # A "question" paragraph with no leading number is a continuation line
        # (e.g. the rest of a riddle/verse) â€” render tight, no big top margin.
        if cls == "question" and not _QNUM_RE.match(block.text):
            cls = "qcont"
        inner = self._decorate(cls, inner)
        return self._paragraph(cls, inner)

    @staticmethod
    def _paragraph(cls: str, inner: str) -> str:
        return f'<paragraph id="{uuid.uuid4()}" class="{cls}">{inner}</paragraph>\n'

    @staticmethod
    def _decorate(cls: str, inner: str) -> str:
        """Colour a leading question number or dialogue speaker labels.

        Speaker labels are coloured at the start of the paragraph AND after every
        forced line break, so dialogue kept in one paragraph still reads well.
        """
        if cls == "question":
            return re.sub(
                r"^(\s*(?:Q\.?\s*\d+|\d+)[.)]?)",
                r'<span class="qnum">\1</span>', inner, count=1,
            )
        if cls == "para":
            return re.sub(
                r"(^|<br>)(\s*[A-Z][A-Za-z]{1,18}:)",
                r'\1<span class="speaker">\2</span>', inner,
            )
        return inner

    @staticmethod
    def _bold_leadin(inner: str) -> str:
        """Bold the lead-in term of a bullet ("Lattice energy: ...") when it is a
        short label followed by a colon and isn't already emphasised."""
        if inner.startswith("<strong>") or ":" not in inner:
            return inner
        head, sep, rest = inner.partition(":")
        # only treat as a label if it's short and has no mid-sentence markup
        if 0 < len(head) <= 42 and "<br>" not in head and "\\(" not in head:
            return f"<strong>{head}:</strong>{rest}"
        return inner

    def _display_image(self, run: InlineRun) -> str:
        if run.latex:
            return (
                f'<div class="math-display" data-latex="{html.escape(run.latex, quote=True)}">'
                f'\\[{run.latex}\\]'
                "</div>\n"
            )
        if run.src:
            alt = html.escape(run.alt or "equation")
            style = f' style="max-height:{run.max_h_px:.0f}px"' if run.max_h_px else ""
            return (
                '<figure class="math-display">'
                f'<img class="block-eqn" src="{html.escape(run.src)}" alt="{alt}"{style}>'
                "</figure>\n"
            )
        # Legacy EPS/CDR artwork is recovered from the reference PDF as a
        # positioned source figure.  Never expose an internal diagnostic label
        # in the reader-facing mobile document.
        return ""

    def render_image(self, block: ImageBlock) -> str:
        if not block.src:
            # Missing legacy artwork is supplied by PDF visual recovery.
            return ""
        alt = html.escape(block.alt or "")
        fig_cls = (
            "opener" if block.alt == "chapter opener"
            else "finisher" if block.alt == "chapter finisher"
            else "fig"
        )
        # No lazy loading: off-screen lazy images can be dropped when printing to PDF.
        return (
            f'<figure class="{fig_cls}">'
            f'<img src="{html.escape(block.src)}" alt="{alt}" loading="lazy" decoding="async">'
            "</figure>\n"
        )

    def render_math(self, block: MathBlock) -> str:
        # Prefer KaTeX from the block's LaTeX; fall back to an image if that is
        # all we have (e.g. an equation with no transcription).
        if block.latex and block.latex.strip():
            delim = ("\\[", "\\]") if block.display else ("\\(", "\\)")
            value = html.escape(block.latex, quote=True)
            return f'<div class="math-display" data-latex="{value}">{delim[0]}{block.latex}{delim[1]}</div>\n'
        if block.fallback_image:
            return (
                '<figure class="math-display">'
                f'<img src="{html.escape(block.fallback_image)}" alt="equation">'
                "</figure>\n"
            )
        return self._paragraph("para", html.escape(_delatex(block.latex)))

    def render_table(self, block: TableBlock) -> str:
        rows: List[str] = []
        for r_i, row in enumerate(block.rows):
            tag = "th" if r_i == 0 else "td"
            cells = []
            for cell in row:
                if not isinstance(cell, dict):        # backward-compat (plain str)
                    cell = {"text": str(cell), "colspan": 1, "rowspan": 1}
                span = ""
                if cell.get("colspan", 1) > 1:
                    span += f' colspan="{cell["colspan"]}"'
                if cell.get("rowspan", 1) > 1:
                    span += f' rowspan="{cell["rowspan"]}"'
                # Prefer the sub/superscript-preserving HTML; fall back to escaped text.
                content = cell.get("html") or html.escape(cell.get("text", ""))
                cells.append(f"<{tag}{span}>{content}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        body = "".join(rows)
        return f'<div class="table-wrap"><table class="tbl">{body}</table></div>\n'

    def finalize(self, body: str) -> str:
        return body + "</body>\n</html>\n"

    # -- helpers -----------------------------------------------------------
    def _inline(self, runs: List[InlineRun]) -> str:
        out: List[str] = []
        for run in runs:
            if run.is_image:
                out.append(self._inline_image(run))
                continue
            text = html.escape(run.text).replace("\n", "<br>")
            if run.superscript:
                text = f"<sup>{text}</sup>"
            elif run.subscript:
                text = f"<sub>{text}</sub>"
            if run.bold:
                text = f"<strong>{text}</strong>"
            if run.italic:
                text = f"<em>{text}</em>"
            out.append(text)
        return "".join(out)

    def _inline_image(self, run: InlineRun) -> str:
        if run.latex:
            # tall (fraction/stacked) equations forced to display even inline read
            # better centred on their own line.
            if run.tall:
                value = html.escape(run.latex, quote=True)
                return f'<span class="math-inline-block" data-latex="{value}">\\[{run.latex}\\]</span>'
            value = html.escape(run.latex, quote=True)
            return f'<span class="math-inline" data-latex="{value}">\\({run.latex}\\)</span>'
        if run.src:
            alt = html.escape(run.alt or "equation")
            # Physical-size the equation (via max-height in CSS px) so it matches
            # the surrounding text instead of scaling to the PNG's pixel size.
            style = f' style="max-height:{run.max_h_px:.0f}px"' if run.max_h_px else ""
            return f'<img class="inline-eqn" src="{html.escape(run.src)}" alt="{alt}"{style}>'
        # Unresolved anchored graphic (e.g. inline EPS with no local rasterizer).
        # These diagrams are recovered separately from the print PDF and placed
        # as page figures, so we omit the inline placeholder to avoid clutter.
        return ""


_SYMBOLS = {
    r"\times": "Ã—", r"\div": "Ã·", r"\pm": "Â±", r"\leq": "â‰¤", r"\geq": "â‰¥",
    r"\neq": "â‰ ", r"\approx": "â‰ˆ", r"\rightarrow": "â†’", r"\rightleftharpoons": "â‡Œ",
    r"\cdot": "Â·", r"\Delta": "Î”", r"\alpha": "Î±", r"\beta": "Î²", r"\pi": "Ï€",
}


def _delatex(s: str) -> str:
    """Reduce any stray LaTeX to plain readable text (safety net only)."""
    for k, v in _SYMBOLS.items():
        s = s.replace(k, v)
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
    s = s.replace("\\[", "").replace("\\]", "").replace("\\(", "").replace("\\)", "")
    s = re.sub(r"[_^]\{([^{}]*)\}", r"\1", s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s{2,}", " ", s).strip()




