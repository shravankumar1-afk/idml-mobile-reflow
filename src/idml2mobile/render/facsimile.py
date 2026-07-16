"""Facsimile renderer â€” a pixel-faithful mobile PDF.

Renders every source (print) PDF page to a high-res image so the output matches
the source 100% (all images, fonts, boxes, diagrams). Two layouts:

* whole-page   : one source page per mobile page, fit to width.
* single-column: detect the two-column gutter, crop each column, and stack them
                 vertically (left then right). The content becomes single column
                 AND the text roughly doubles in size (each column fills the
                 mobile width) â€” still a 100% visual match, just reflowed by
                 column. Full-width pages (no clear gutter) are kept whole.

Text remains an image (not selectable). Requires the print PDF and PyMuPDF.
"""
from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Dict, List

from idml2mobile.config import MobileProfile


class FacsimileRenderer:
    def __init__(self, profile: MobileProfile, dpi: int = 200, jpeg_quality: int = 82,
                 single_column: bool = True) -> None:
        self.profile = profile
        self.dpi = dpi
        self.jpeg_quality = jpeg_quality
        self.single_column = single_column

    # -- public ------------------------------------------------------------
    def build(self, source_pdf: Path, out_dir: Path, progress_callback=None) -> Dict:
        import fitz  # PyMuPDF

        out_dir = Path(out_dir)
        images_dir = out_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        src = fitz.open(str(source_pdf))
        target_w_pt = self.profile.page_width * 72.0 / 96.0   # 360 CSS px -> 270 pt
        zoom = self.dpi / 72.0
        out_pdf = fitz.open()
        rels: List[str] = []
        tiles = 0
        try:
            for i in range(src.page_count):
                page = src[i]
                # Covers and opener spreads often contain artwork crossing the
                # centre; preserve page 1 whole. For body pages, split only when
                # live PDF text proves there are two independent columns.
                clips = (self._column_clips(fitz, page)
                         if self.single_column and i > 0 else [page.rect])
                for j, clip in enumerate(clips):
                    if clip.width < 8 or clip.height < 8:
                        continue
                    scale = target_w_pt / clip.width
                    target_h_pt = clip.height * scale
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip,
                                          alpha=False)
                    jpg = pix.tobytes("jpg", jpg_quality=self.jpeg_quality)
                    name = f"page_{i + 1:03d}_{j + 1}.jpg"
                    (images_dir / name).write_bytes(jpg)
                    rels.append(f"images/{name}")
                    new_page = out_pdf.new_page(width=target_w_pt, height=target_h_pt)
                    # Place the original PDF region as vector content. This is
                    # visually exact and preserves searchable/selectable source
                    # text, embedded fonts, line art, equations and tables.
                    new_page.show_pdf_page(
                        new_page.rect, src, i, clip=clip, keep_proportion=False
                    )
                    tiles += 1
                if progress_callback:
                    progress_callback(i + 1, src.page_count, tiles)
            out_pdf.save(str(out_dir / "mobile.pdf"), deflate=True, garbage=4)
            pages = src.page_count
        finally:
            out_pdf.close()
            src.close()

        self._write_html(out_dir, rels)
        return {"pages": pages, "tiles": tiles, "mode": "source-faithful",
                "single_column": self.single_column,
                "pdf_content": "vector source clips"}

    # -- column detection --------------------------------------------------
    def _column_clips(self, fitz, page):
        # Preserve full-page scanned artwork; column detection would crop it.
        try:
            page_images = page.get_images(full=True)
            words = page.get_text("words")
            if len(page_images) == 1 and not words:
                return [page.rect]
        except Exception:
            pass

        """Return full-height left/right clips when PDF text geometry proves
        that the page has two independent columns; otherwise return the whole
        page. Full-height clips deliberately retain every diagram, table, rule,
        header and footer?visual completeness takes priority over trimming.

        The text-geometry detector runs before the raster fallback because
        textured textbook backgrounds can make a real gutter look non-empty in
        pixels.
        """
        geometric = self._text_column_clips(fitz, page)
        if geometric:
            return geometric

        """Raster fallback for pages whose live text is unavailable.

        Detection keys on DARK TEXT pixels, not brightness â€” the pages have a
        full blue background, so a white-gutter test fails; instead the gutter is
        the central column band that contains (almost) no dark text.
        """
        from PIL import Image

        r = page.rect
        W, H = r.width, r.height
        lz = 110.0 / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(lz, lz), colorspace=fitz.csGRAY,
                              alpha=False)
        im = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        # Binary "text" map: dark pixel -> 255, everything else (incl. background) -> 0.
        binary = im.point(lambda v: 255 if v < 130 else 0)
        w, h = binary.size
        col = binary.resize((w, 1), Image.BILINEAR).load()   # ~255 * fraction-dark per column
        dark = [col[x, 0] for x in range(w)]
        median = sorted(dark)[len(dark) // 2] or 1

        lo, hi = int(0.40 * w), int(0.60 * w)
        gx = min(range(lo, hi), key=lambda x: dark[x]) if hi > lo else w // 2
        # A gutter is a central column with far less text than the page's typical
        # column (the blue background adds baseline noise, so this is relative).
        if median < 6 or dark[gx] >= 0.6 * median:
            return [self._trim(fitz, binary, W, H, 0.0, W) or r]
        gutter = (gx / w) * W
        clips = [self._trim(fitz, binary, W, H, 0.0, gutter),
                 self._trim(fitz, binary, W, H, gutter, W)]
        clips = [c for c in clips if c is not None]
        return clips or [r]

    @staticmethod
    def _text_column_clips(fitz, page):
        words = [w for w in page.get_text("words") if str(w[4]).strip()]
        blocks = [b for b in page.get_text("blocks")
                  if b[6] == 0 and str(b[4]).strip()]
        if len(words) < 40 or len(blocks) < 6:
            return None
        W, H = page.rect.width, page.rect.height
        lo, hi = 0.42 * W, 0.58 * W
        candidates = []
        step = max(1.0, W / 500.0)
        x = lo
        while x <= hi:
            crossings = sum(1 for w in words if w[0] < x < w[2])
            candidates.append((crossings, x))
            x += step
        minimum = min(c for c, _ in candidates)
        quiet = [x for c, x in candidates if c == minimum]
        gutter = sum(quiet) / len(quiet)

        left_words = sum(1 for w in words if (w[0] + w[2]) / 2 < gutter)
        right_words = len(words) - left_words
        left_blocks = sum(1 for b in blocks if b[2] <= gutter + 8)
        right_blocks = sum(1 for b in blocks if b[0] >= gutter - 8)
        crossing_blocks = sum(1 for b in blocks if b[0] < gutter - 8 and b[2] > gutter + 8)
        if (left_words < 20 or right_words < 20 or left_blocks < 3 or right_blocks < 3
                or crossing_blocks > max(4, int(0.25 * len(blocks)))):
            return None
        # Small overlap protects strokes and labels touching the gutter.
        overlap = 20.0
        return [fitz.Rect(0, 0, min(W, gutter + overlap), H),
                fitz.Rect(max(0, gutter - overlap), 0, W, H)]

    @staticmethod
    def _trim(fitz, binary, W, H, x0_pt, x1_pt):
        """Trim leading/trailing text-free rows from a column region -> tight clip."""
        from PIL import Image

        w, h = binary.size
        cx0 = max(0, int(x0_pt / W * w))
        cx1 = min(w, int(x1_pt / W * w))
        if cx1 - cx0 < 4:
            return None
        strip = binary.crop((cx0, 0, cx1, h)).resize((1, h), Image.BILINEAR).load()
        rowdark = [strip[0, y] for y in range(h)]
        thresh = 4
        top = next((y for y in range(h) if rowdark[y] > thresh), None)
        bot = next((y for y in range(h - 1, -1, -1) if rowdark[y] > thresh), None)
        if top is None or bot is None or bot <= top:
            return None
        pad = max(2, int(0.012 * h))
        y0 = max(0, top - pad) / h * H
        y1 = min(h, bot + 1 + pad) / h * H
        return fitz.Rect(x0_pt, y0, x1_pt, y1)

    # -- html --------------------------------------------------------------
    def _write_html(self, out_dir: Path, rels) -> None:
        css_dir = out_dir / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        (css_dir / "styles.css").write_text(
            "html,body{margin:0;padding:0;background:#e6eef8;}"
            "img{display:block;width:100%;height:auto;margin:0 auto 6px;"
            "border:1px solid #cdd;}",
            encoding="utf-8",
        )
        imgs = "\n".join(
            f'<img src="{_html.escape(s)}" alt="page tile {i + 1}" loading="lazy">'
            for i, s in enumerate(rels)
        )
        html_doc = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f'<meta name="viewport" content="width={self.profile.page_width}, '
            'initial-scale=1"><title>Facsimile</title>'
            '<link rel="stylesheet" href="css/styles.css"></head><body>'
            f"{imgs}</body></html>"
        )
        (out_dir / "index.html").write_text(html_doc, encoding="utf-8")
