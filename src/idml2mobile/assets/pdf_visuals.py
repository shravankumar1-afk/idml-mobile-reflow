"""Recover visuals from the source print PDF that cannot be rebuilt from IDML.

Some artwork in an InDesign document is native vector art (chapter-opener
infographics, banners) or placed EPS that has no local rasterizer (no
Ghostscript). The exported print PDF, however, has the identical page layout,
so we rasterize those regions straight from it with PyMuPDF.

Two extractors:
  * chapter opener  -> the graphic band above the first body paragraph on p.1
  * page figures    -> graphic bands on later pages that hold little/no text
Both are best-effort and degrade to "nothing recovered" if PyMuPDF is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class VisualRecord:
    page_index: int
    y0: float
    rel_path: str          # path relative to the output dir (images/...)
    width_px: int
    height_px: int
    kind: str              # "opener" | "figure" | "finisher"
    anchor_before: str = ""
    anchor_after: str = ""


class PDFVisualExtractor:
    def __init__(self, pdf_path: Path, images_dir: Path, images_subdir: str = "images",
                 dpi: int = 200) -> None:
        self.pdf_path = Path(pdf_path)
        self.images_dir = Path(images_dir)
        self.images_subdir = images_subdir
        self.zoom = dpi / 72.0

    # -- public ------------------------------------------------------------
    def available(self) -> bool:
        try:
            import fitz  # noqa: F401
            return True
        except Exception:
            return False

    def extract(self, want_figures: bool = True) -> List[VisualRecord]:
        try:
            import fitz
        except Exception:
            return []
        if not self.pdf_path.exists():
            return []

        self.images_dir.mkdir(parents=True, exist_ok=True)
        out: List[VisualRecord] = []
        doc = fitz.open(str(self.pdf_path))
        try:
            opener = self._opener(fitz, doc)
            if opener:
                out.append(opener)
            finishers = self._finishers(fitz, doc)
            out.extend(finishers)
            if want_figures:
                out.extend(self._figures(
                    fitz, doc, skip_pages={0} | {r.page_index for r in finishers}
                ))
        finally:
            doc.close()
        return out

    # -- chapter opener ----------------------------------------------------
    def _opener(self, fitz, doc) -> Optional[VisualRecord]:
        if doc.page_count == 0:
            return None
        page = doc[0]
        W, H = page.rect.width, page.rect.height
        longs = [b for b in page.get_text("blocks")
                 if b[6] == 0 and len(b[4].strip()) > 120]
        body_top = min((b[1] for b in longs), default=H * 0.5)
        if body_top < 60:                         # no real header band
            return None
        # need actual graphic ink above the body text
        has_graphic = any(d["rect"].y0 < body_top - 20 for d in page.get_drawings()) \
            or len(page.get_images()) > 0
        if not has_graphic:
            return None
        clip = fitz.Rect(6, 6, W - 6, max(body_top - 4, 120))
        return self._render(fitz, page, clip, 0, kind="opener", name="opener")

    def _finishers(self, fitz, doc) -> List[VisualRecord]:
        """Preserve designed chapter-ending QR/test artwork as one exact crop."""
        records: List[VisualRecord] = []
        for page_index, page in enumerate(doc):
            hits = page.search_for("Chapter Complete? Take The Test!")
            if not hits:
                continue
            y0 = max(0.0, min(r.y0 for r in hits) - 8.0)
            clip = fitz.Rect(6, y0, page.rect.width - 6, page.rect.height - 6)
            rec = self._render(
                fitz, page, clip, page_index, kind="finisher",
                name=f"finisher_p{page_index}",
            )
            if rec:
                records.append(rec)
        return records
    # -- per-page figures (column-aware row-band detection) ----------------
    def _figures(self, fitz, doc, skip_pages) -> List[VisualRecord]:
        records: List[VisualRecord] = []
        for pi in range(doc.page_count):
            if pi in skip_pages:
                continue
            page = doc[pi]
            for j, band in enumerate(self._page_figures(fitz, page)):
                rec = self._render(fitz, page, band, pi, kind="figure",
                                   name=f"fig_p{pi}_{j}")
                if rec:
                    records.append(rec)
        return records

    def _page_figures(self, fitz, page) -> list:
        """A diagram is a vertical band, within one text column, made of GRAPHIC
        ink (drawing strokes) after removing live-text pixels. Removing the text
        (not whole text rows) keeps labeled diagrams intact â€” the strokes around
        the labels survive, so the band is detected and cropped whole."""
        from PIL import Image, ImageDraw

        W, H = page.rect.width, page.rect.height
        lz = 110.0 / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(lz, lz), colorspace=fitz.csGRAY, alpha=False)
        im = Image.frombytes("L", [pix.width, pix.height], pix.samples)
        w, h = im.size
        # Dark-ink map: text/line art is dark; the blue page background is not.
        binary = im.point(lambda v: 255 if v < 115 else 0)
        # Graphic-only map = ink with live-text pixels erased.
        gmap = binary.copy()
        draw = ImageDraw.Draw(gmap)
        for wd in page.get_text("words"):
            x0, y0, x1, y1 = wd[0], wd[1], wd[2], wd[3]
            draw.rectangle([x0 / W * w - 1, y0 / H * h - 1,
                            x1 / W * w + 1, y1 / H * h + 1], fill=0)
        # Saturation map (HSV S channel) to tell grayscale line-art diagrams from
        # coloured UI (blue table headers/bars, orange Key-Note/QR/3D-Model boxes).
        try:
            sat = page.get_pixmap(matrix=fitz.Matrix(110 / 72.0, 110 / 72.0), alpha=False)
            rgb = Image.frombytes("RGB", [sat.width, sat.height], sat.samples)
            satmap = rgb.convert("HSV").getchannel("S")
        except Exception:
            satmap = None

        bands: list = []
        for (cx0, cx1) in self._columns(binary, W, page):
            bands.extend(self._column_bands(fitz, gmap, satmap, W, H, cx0, cx1))
        bands.sort(key=lambda r: (round(r.y0), round(r.x0)))
        return bands[:20]                             # chemistry pages contain many structures

    @staticmethod
    def _columns(binary, W, page=None):
        from PIL import Image

        # Prefer live-text geometry on textured two-column pages.
        if page is not None:
            try:
                import fitz
                from idml2mobile.render.facsimile import FacsimileRenderer
                clips = FacsimileRenderer._text_column_clips(fitz, page)
                if clips and len(clips) == 2:
                    gutter = (clips[0].x1 + clips[1].x0) / 2.0
                    return [(0.0, gutter), (gutter, W)]
            except Exception:
                pass
        w, _ = binary.size
        col = binary.resize((w, 1), Image.BILINEAR).load()
        dark = [col[x, 0] for x in range(w)]
        median = sorted(dark)[len(dark) // 2] or 1
        lo, hi = int(0.40 * w), int(0.60 * w)
        gx = min(range(lo, hi), key=lambda x: dark[x]) if hi > lo else w // 2
        if median >= 6 and dark[gx] < 0.6 * median:      # clear central gutter
            g = (gx / w) * W
            return [(0.0, g), (g, W)]
        return [(0.0, W)]

    @staticmethod
    def _column_bands(fitz, gmap, satmap, W, H, cx0, cx1):
        from PIL import Image

        w, h = gmap.size
        px0, px1 = max(0, int(cx0 / W * w)), min(w, int(cx1 / W * w))
        if px1 - px0 < 8:
            return []
        strip = gmap.crop((px0, 0, px1, h)).resize((1, h), Image.BILINEAR).load()
        gink = [strip[0, y] for y in range(h)]           # non-text (graphic) ink per row

        fig = [g > 4 for g in gink]                       # a row with drawing strokes
        gap_rows = max(1, int(18 * h / H))               # bridge ~30pt internal gaps
        min_h_pt = 20.0

        bands = []
        y = 0
        while y < h:
            if not fig[y]:
                y += 1
                continue
            y0 = last = y
            gap = 0
            y += 1
            while y < h:
                if fig[y]:
                    last = y
                    gap = 0
                else:
                    gap += 1
                    if gap > gap_rows:
                        break
                y += 1
            y1 = last + 1
            fig_rows = sum(1 for yy in range(y0, y1) if fig[yy])
            density = sum(gink[y0:y1]) / (255.0 * max(1, y1 - y0))
            if (y1 - y0) / h * H >= min_h_pt \
                    and fig_rows >= max(8, int(0.2 * (y1 - y0))) \
                    and density < 0.5 \
                    and PDFVisualExtractor._color_frac(satmap, px0, px1, y0, y1) < 0.25:
                pad = 16 * h / H
                bands.append(fitz.Rect(
                    cx0 + 2, max(0, y0 - pad) / h * H,
                    cx1 - 2, min(h, y1 + pad) / h * H,
                ))
        return bands

    @staticmethod
    def _color_frac(satmap, px0, px1, y0, y1) -> float:
        """Fraction of strongly-coloured pixels in a band. Grayscale line-art
        diagrams are ~0; coloured UI (blue bars/headers, orange boxes) is high."""
        if satmap is None:
            return 0.0
        from PIL import Image
        crop = satmap.crop((px0, y0, px1, y1))
        if crop.width < 2 or crop.height < 2:
            return 0.0
        small = crop.resize((min(80, crop.width), min(80, crop.height)), Image.BILINEAR)
        data = list(small.getdata())
        if not data:
            return 0.0
        strong = sum(1 for s in data if s > 90)          # S>~0.35 => saturated colour
        return strong / len(data)

    def _render(self, fitz, page, clip, page_index, kind, name) -> Optional[VisualRecord]:
        clip = clip & page.rect
        if clip.width < 20 or clip.height < 20:
            return None
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), clip=clip)
        fname = f"{name}.png"
        pix.save(str(self.images_dir / fname))
        text_blocks = [
            b for b in page.get_text("blocks")
            if b[6] == 0 and str(b[4]).strip()
            and b[2] >= clip.x0 and b[0] <= clip.x1
        ]
        above = [b for b in text_blocks if b[3] <= clip.y0 + 2]
        below = [b for b in text_blocks if b[1] >= clip.y1 - 2]
        anchor_before = max(above, key=lambda b: b[3])[4] if above else ""
        anchor_after = min(below, key=lambda b: b[1])[4] if below else ""
        return VisualRecord(
            page_index=page_index,
            y0=float(clip.y0),
            rel_path=f"{self.images_subdir}/{fname}",
            width_px=pix.width,
            height_px=pix.height,
            kind=kind,
            anchor_before=str(anchor_before),
            anchor_after=str(anchor_after),
        )

