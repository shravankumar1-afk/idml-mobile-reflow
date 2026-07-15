"""ConversionPipeline Ã¢â‚¬â€ the Facade over the whole conversion.

One entry point (`convert`) orchestrates validation, unpacking, parsing,
reading-order reconstruction, cleanup, model building, HTML/PDF rendering, and
QA. It is a Subject, so callers attach observers for progress/logging. Each
stage is small and delegates to a dedicated component.
"""
from __future__ import annotations

import json
import math
from difflib import SequenceMatcher
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from idml2mobile.assets.repository import AssetRepository
from idml2mobile.cleanup.passes import CleanupChain
from idml2mobile.config import ConversionConfig, MobileProfile
from idml2mobile.idml.adapter import IDMLAdapter
from idml2mobile.idml.package import IDMLPackage
from idml2mobile.idml.validator import InputValidator, ValidationResult
from idml2mobile.mathconv.equations import EquationMap
from idml2mobile.mathconv.mathml import extract_mathtype_latex
from idml2mobile.assets.pdf_visuals import PDFVisualExtractor
from idml2mobile.model.blocks import (
    Block, BlockType, Document, ImageBlock, TableBlock, TextBlock,
)
from idml2mobile.model.builder import DocumentBuilder
from idml2mobile.observers.base import Level, Subject
from idml2mobile.parsers.base import Frame, PageInfo, RawStory
from idml2mobile.parsers.factory import ParserFactory
from idml2mobile.qa.checks import QAReport, QAValidator
from idml2mobile.reading_order.strategies import get_strategy
from idml2mobile.render.html_renderer import HTMLRenderer
from idml2mobile.render.pdf_renderer import PDFRenderer, PlaywrightNotInstalled
from idml2mobile.render.style_builder import StyleBuilder

_FONT_EXT = {".ttf", ".otf", ".ttc"}
# DPI used to rasterize WMF/EMF equations (see assets/convert.py _WMF_DPI).
EQ_RENDER_DPI = 600
# Short callout labels ("Key Note" tabs) Ã¢â‚¬â€ rendered as a tab, not wrapped in a box.
# ("advanced learning" is intentionally excluded so those decorative tags drop out.)
_CALLOUT_LABEL_RE = re.compile(r"key\s*note|remember|do\s*you\s*know", re.I)
# Example ribbon markers ("Ex-9", "Ex 9", "Ex.9").
_EX_LABEL_RE = re.compile(r"^\s*ex[\s.\-]*\d+\b", re.I)


@dataclass
class ConversionResult:
    output_dir: Path
    document: Optional[Document] = None
    validation: Optional[ValidationResult] = None
    qa: Optional[QAReport] = None
    html_path: Optional[Path] = None
    pdf_path: Optional[Path] = None
    asset_records: List = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class ConversionPipeline(Subject):
    def __init__(self, config: ConversionConfig) -> None:
        super().__init__()
        self.config = config
        self.profile: MobileProfile = config.profile
        self.adapter = IDMLAdapter()
        self._equation_map = EquationMap.load(getattr(config, "equations_path", None))

    # -- public API --------------------------------------------------------
    def convert(self) -> ConversionResult:
        cfg = self.config
        started = time.perf_counter()
        out = cfg.output_dir
        result = ConversionResult(output_dir=out)

        self.emit("validate", "Validating input", progress=0.0)
        validation = InputValidator().validate(cfg.input_path)
        result.validation = validation
        if not validation.ok:
            for err in validation.errors:
                self.emit("validate", err, level=Level.ERROR)
            raise ValueError("Input validation failed: " + "; ".join(validation.errors))
        for w in validation.warnings:
            self.emit("validate", w, level=Level.WARNING)

        # Safety: never write output into the source package (it mingles with the
        # .idml / Links / fonts and has led to accidental source deletion).
        self._guard_output_location(out, validation)
        out.mkdir(parents=True, exist_ok=True)
        self.emit(
            "validate",
            f"{len(validation.present_links)} links present, "
            f"{len(validation.missing_links)} missing, {len(validation.fonts)} fonts",
            progress=1.0,
        )

        # Facsimile mode: render the source PDF pages 1:1 (true 100% match).
        if cfg.mode in {"facsimile", "source-faithful"}:
            return self._convert_facsimile(validation, out, result, started)

        pkg = IDMLPackage(validation.idml_file)
        try:
            pkg.unpack()
            self.emit("unpack", f"Unpacked IDML to {pkg.root}", progress=1.0)

            pages, frames = self._parse_spreads(pkg)
            stories = self._parse_stories(pkg)
            self.emit(
                "parse",
                f"{len(pages)} pages, {len(frames)} frames, {len(stories)} stories",
                progress=1.0,
            )

            repo = AssetRepository(links_dir=validation.links_dir, output_dir=out)
            blocks = self._reconstruct(frames, stories, repo, pkg)
            if self.config.convert_assets:
                self._resolve_inline_images(blocks, repo)
            result.asset_records = repo.records()
            placed = sum(1 for r in result.asset_records if r.found and r.output_rel)
            self.emit(
                "reading-order",
                f"{len(blocks)} blocks ordered; {placed}/{len(result.asset_records)} assets placed",
                progress=1.0,
            )

            blocks = CleanupChain().run(blocks)
            blocks = self._drop_layout_artifacts(blocks)
            self.emit("cleanup", f"{len(blocks)} blocks after cleanup", progress=1.0)

            if validation.reference_pdf:
                blocks = self._align_blocks_to_pdf(blocks, validation.reference_pdf)
            if self.config.recover_visuals and validation.reference_pdf:
                blocks = self._recover_visuals(blocks, validation.reference_pdf, out)

            # Merge split callout frames into single boxes (Key Note label on top).
            blocks = self._merge_anchored_runs(blocks)
            # Wrap each worked example (question + "Ex-N" ribbon + solution) in a
            # box, so exercise questions sit INSIDE their box as in the source.
            blocks = self._group_examples(blocks)
            blocks = self._hoist_question_headers(blocks)

            document = self._build_document(blocks, validation)
            result.document = document
            self.emit("model", f"{len(document.sections)} sections built", progress=1.0)

            result.html_path = self._write_html_and_assets(document, out, validation)
            self.emit("render-html", f"Wrote {result.html_path.name}", progress=1.0)

            if cfg.render_pdf:
                result.pdf_path = self._render_pdf(result.html_path, out)

            self.emit("qa", "Running QA checks", progress=0.5)
            coverage = self._coverage(stories, document)
            qa = QAValidator(self.profile).validate(
                out, document=document, asset_records=result.asset_records,
                run_dynamic=cfg.render_pdf, coverage=coverage,
            )
            result.qa = qa
            level = Level.INFO if qa.passed else Level.WARNING
            self.emit("qa", f"QA {'passed' if qa.passed else 'has issues'}: "
                            f"{len(qa.errors)} errors, {len(qa.warnings)} warnings",
                      level=level, progress=1.0)

            result.stats = self._compute_stats(
                document, result.asset_records,
                elapsed=time.perf_counter() - started, source_pages=len(pages),
            )
            self._write_stats(out, result.stats)
            s = result.stats
            self.emit(
                "stats",
                f"Time {s['elapsed_human']} | "
                f"~{s['text_tokens_est']:,} tokens | {s['words']:,} words | "
                f"{s['images_placed']} images | {s['pages']} pages",
                progress=1.0, **s,
            )
        finally:
            if not cfg.keep_temp:
                pkg.cleanup()
        self.emit("done", f"Output ready in {out}", progress=1.0)
        return result

    @staticmethod
    def _guard_output_location(out: Path, validation: ValidationResult) -> None:
        """Refuse an output folder that is the source package folder itself (or
        the folder directly holding the .idml), so we never overwrite/mingle
        with the user's source files."""
        try:
            out_res = out.resolve()
            pkg_dir = Path(validation.input_dir).resolve()
            idml_parent = Path(validation.idml_file).resolve().parent
        except Exception:
            return
        if out_res in (pkg_dir, idml_parent):
            raise ValueError(
                "Output folder must not be the source package folder "
                f"({out_res}). Choose a separate output location "
                "(e.g. a 'mobile_output' folder outside the package)."
            )

    def _convert_facsimile(self, validation, out: Path, result, started: float):
        """Render the source print PDF page-for-page to a mobile-width facsimile."""
        from idml2mobile.render.facsimile import FacsimileRenderer

        if not validation.reference_pdf:
            raise ValueError(
                "Facsimile mode needs the source/print PDF in the package "
                "(no .pdf found next to the .idml)."
            )
        self.emit("facsimile", "Rendering source pages to mobile-width images",
                  progress=0.2)
        info = FacsimileRenderer(self.profile).build(validation.reference_pdf, out)
        result.html_path = out / "index.html"
        self.emit("facsimile", f"Rendered {info['pages']} pages", progress=0.9)

        qa = QAValidator(self.profile).validate(out, document=None, run_dynamic=False)
        result.qa = qa
        result.stats = {
            "mode": "source-faithful",
            "source_pages": info["pages"],
            "mobile_tiles": info.get("tiles", info["pages"]),
            "pdf_content": info.get("pdf_content", "source clips"),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "elapsed_human": self._fmt_duration(time.perf_counter() - started),
            "note": "source PDF regions preserved as vector mobile pages (100% visual match)",
        }
        self._write_stats(out, result.stats)
        self.emit("done", f"Facsimile output ready in {out}", progress=1.0)
        return result

    # -- stages ------------------------------------------------------------
    def _parse_spreads(self, pkg: IDMLPackage):
        pages: List[PageInfo] = []
        frames: List[Frame] = []
        spread_names = pkg.spread_order() or [p.name for p in pkg.spreads()]
        base = 0
        for name in spread_names:
            path = pkg.root / "Spreads" / name
            if not path.exists():
                continue
            parser = ParserFactory.for_spread(path, page_base_index=base)
            spr_pages, spr_frames = parser.parse()
            pages.extend(spr_pages)
            frames.extend(spr_frames)
            base += len(spr_pages)
        return pages, frames

    def _parse_stories(self, pkg: IDMLPackage) -> Dict[str, RawStory]:
        stories: Dict[str, RawStory] = {}
        for path in pkg.stories():
            raw = ParserFactory.for_story(path).parse()
            if raw is not None:
                stories[raw.story_id] = raw
        return stories

    def _reconstruct(self, frames, stories, repo: AssetRepository, pkg) -> List[Block]:
        strategy = get_strategy(self.config.reading_order_strategy, pkg.story_order())
        groups = strategy.order(frames)
        blocks: List[Block] = []
        self._box_seq = 0
        visited_boxes: set = set()
        order = 0
        for group in groups:
            if group.kind == "story":
                raw = stories.get(group.story_id)
                if raw is None:
                    continue
                sub: List[Block] = []
                self._expand_story(raw, stories, visited_boxes, 0, sub, depth=0)
                for block in sub:
                    block.page = group.page_index
                    block.column = group.column
                    block.y = group.y
                    block.order_key = order
                    order += 1
                    blocks.append(block)
            elif group.kind == "image" and group.frame is not None:
                block = self._image_block(group.frame, repo)
                if block is not None:
                    block.order_key = order
                    order += 1
                    blocks.append(block)
        return blocks

    def _expand_story(self, raw: RawStory, stories, visited: set, box_group: int,
                      sink: List[Block], depth: int) -> None:
        """Expand a story's paragraphs into blocks, recursing into anchored text
        frames (Key Notes / callout boxes) so their content is not lost."""
        for para in raw.paragraphs:
            block = self.adapter.paragraph_to_block(para)
            if block is not None and not (isinstance(block, TextBlock) and block.is_empty()):
                block.box_group = box_group
                block.anchored = depth > 0
                sink.append(block)
            # Tables anchored in this paragraph -> TableBlock(s).
            for run in para.runs:
                if run.table:
                    tb = TableBlock(rows=run.table)
                    tb.box_group = box_group
                    tb.anchored = depth > 0
                    sink.append(tb)
            # Recurse into anchored text-frame boxes referenced in this paragraph.
            # Only SUBSTANTIAL frames (Key Notes / definitions / callouts) become
            # boxes. Tiny frames Ã¢â‚¬â€ infographic labels ("51%"), single MCQ options
            # ("O", "H"), matching-grid cells ("Solubility") Ã¢â‚¬â€ are layout fragments
            # that turn into repeated-word garbage when linearised, so we skip them.
            if depth < 6:
                for run in para.runs:
                    bid = run.textframe_story
                    if not (bid and bid in stories and bid not in visited):
                        continue
                    visited.add(bid)
                    box_raw = stories[bid]
                    box_text = " ".join(p.text for p in box_raw.paragraphs).strip()
                    tokens = box_text.split()
                    words = [w for w in tokens if len(w) >= 3]
                    has_content_assets = any(
                        child_run.image_uri or child_run.table or child_run.textframe_story
                        for child_para in box_raw.paragraphs
                        for child_run in child_para.runs
                    )
                    if has_content_assets:
                        # Equation-only anchored stories contain no prose, but
                        # their MathType/diagram links are real source content.
                        self._expand_story(
                            box_raw, stories, visited, box_group, sink, depth + 1
                        )
                    elif len(box_text) <= 24 and (_CALLOUT_LABEL_RE.search(box_text)
                                                or _EX_LABEL_RE.search(box_text)):
                        # "Key Note" / "Ex-9" style label -> inline tab (no box).
                        self._expand_story(box_raw, stories, visited, box_group,
                                           sink, depth + 1)
                    elif len(box_text) >= 40 and len(words) >= 6:
                        # Substantial callout / definition -> a bordered box.
                        self._box_seq += 1
                        self._expand_story(box_raw, stories, visited, self._box_seq,
                                           sink, depth + 1)
                    elif len(tokens) >= 3 and len(box_text) >= 12:
                        # Multi-word phrase (e.g. an MCQ option) -> inline, no box.
                        self._expand_story(box_raw, stories, visited, box_group,
                                           sink, depth + 1)
                    # else: 1-2 token fragment (labels/cells "51%", "O", "Solubility")
                    #       -> skip; linearising these produces repeated-word noise.

    def _resolve_inline_images(self, blocks, repo: AssetRepository) -> None:
        """Resolve every inline anchored graphic (e.g. MathType WMF).

        If the equation has a LaTeX transcription in the equation map, attach it
        so the renderer emits KaTeX. Otherwise convert the source to a web-safe
        image via the AssetRepository so it can be shown as a fallback."""
        eqmap = self._equation_map
        for block in blocks:
            runs = getattr(block, "runs", None)
            if not runs:
                continue
            for run in runs:
                if not (run.is_image and run.original_ref):
                    continue
                hit = eqmap.lookup(run.original_ref)
                if hit is not None:
                    run.latex = hit.latex
                    # display flag is advisory; renderer still decides from context
                    # unless the map explicitly forces it.
                    if hit.display is not None:
                        run.tall = bool(hit.display)
                    continue
                # MathType WMFs embed complete MathML. This is lossless and
                # makes every equation editable/KaTeX-rendered without OCR.
                source = repo.source_path(run.original_ref)
                latex = extract_mathtype_latex(source) if source else None
                if latex:
                    run.latex = latex
                    # Long or structurally stacked MathType expressions need a
                    # full-width math row on narrow mobile pages.  This keeps
                    # KaTeX selectable while preventing document-level overflow.
                    run.tall = bool(
                        len(latex) > 70
                        or "\\begin{" in latex
                        or latex.count("\\frac") >= 2
                    )
                    continue
                # No MathML/LaTeX payload -> fall back to the equation image.
                record = repo.resolve(run.original_ref)
                if record.found and record.output_rel:
                    run.src = record.output_rel
                    run.alt = record.original_name
                    w, h = self._png_size(repo.output_dir / record.output_rel)
                    run.tall = bool(w and h and (h / w) >= 0.45)
                    # Equation PNGs are rendered at EQ_RENDER_DPI; convert the
                    # pixel height back to physical CSS px so every equation
                    # displays at a size consistent with the body text.
                    if h:
                        run.max_h_px = round(h * 96.0 / EQ_RENDER_DPI, 1)

    @staticmethod
    def _png_size(png_path: Path):
        try:
            from PIL import Image
            with Image.open(png_path) as im:
                return im.size
        except Exception:
            return (0, 0)

    @staticmethod
    def _drop_layout_artifacts(blocks: List[Block]) -> List[Block]:
        """Drop bounded print-navigation/statistics panels, not document content."""
        out = list(blocks)
        i = 0
        while i < len(out):
            block = out[i]
            text = block.text.strip().lower() if isinstance(block, TextBlock) else ""
            if text != "years paper":
                i += 1
                continue
            j = i + 1
            found_end = False
            while j < min(len(out), i + 12):
                candidate = out[j]
                candidate_text = (candidate.text.strip().lower()
                                  if isinstance(candidate, TextBlock) else "")
                if candidate_text == "solutions":
                    found_end = True
                    break
                if re.fullmatch(r"\d+\s*sets?", candidate_text):
                    j += 1
                    found_end = True
                    break
                j += 1
            if found_end:
                del out[i:j]
            else:
                i += 1
        return out

    @staticmethod
    def _pdf_norm(text: str) -> str:
        text = (text or "").lower().replace("\u00ad", "")
        return re.sub(r"[^a-z0-9%]+", " ", text).strip()

    def _align_blocks_to_pdf(self, blocks: List[Block], pdf_path: Path) -> List[Block]:
        """Align reflow blocks to source page/y using the print PDF's live text.

        A threaded InDesign story spans many frames/pages, so story-level frame
        geometry alone assigns every paragraph to the first frame. Text matching
        restores the paragraph-level source anchor needed for inline figures and
        anchored labels.
        """
        try:
            import fitz
        except Exception:
            return blocks
        candidates = []
        doc = fitz.open(str(pdf_path))
        try:
            for page_index, page in enumerate(doc):
                for raw in page.get_text("blocks"):
                    if raw[6] != 0:
                        continue
                    norm = self._pdf_norm(raw[4])
                    if len(norm) >= 8:
                        candidates.append((page_index, float(raw[1]), norm))
        finally:
            doc.close()
        cursor = 0
        matched = 0
        for block in blocks:
            if not isinstance(block, TextBlock):
                continue
            needle = self._pdf_norm(block.text)
            if len(needle) < 8:
                continue
            probe = needle[:120]
            best_i, best_score = -1, 0.0
            lo, hi = max(0, cursor - 8), min(len(candidates), cursor + 350)
            for idx in range(lo, hi):
                candidate = candidates[idx][2]
                if probe[:35] and probe[:35] in candidate:
                    score = 1.0
                elif candidate[:35] and candidate[:35] in needle:
                    score = 0.92
                else:
                    score = SequenceMatcher(None, probe, candidate[:max(120, len(probe))]).ratio()
                if score > best_score:
                    best_i, best_score = idx, score
                    if score == 1.0:
                        break
            if best_i >= 0 and best_score >= 0.55:
                block.page, block.y = candidates[best_i][0], candidates[best_i][1]
                cursor = max(cursor, best_i)
                matched += 1
        # Monotonic fallback for threaded stories whose exact text was not found.
        # Distribute unmatched blocks across source pages so recovered diagrams do not collapse.
        if candidates:
            total_text = sum(1 for b in blocks if isinstance(b, TextBlock))
            seen_text = 0
            for block in blocks:
                if not isinstance(block, TextBlock):
                    continue
                if self._pdf_norm(block.text) and block.page == 0 and total_text > 1:
                    est = min(len(candidates) - 1, round(seen_text * (len(candidates) - 1) / (total_text - 1)))
                    block.page, block.y = candidates[est][0], candidates[est][1]
                seen_text += 1

        last_text = None
        for block in blocks:
            if isinstance(block, TextBlock):
                last_text = block
            elif isinstance(block, TableBlock) and last_text is not None:
                block.page = last_text.page
                block.y = float(last_text.y) + 0.1
        self.emit("alignment", f"Aligned {matched}/{len(blocks)} blocks to source PDF positions",
                  progress=1.0)
        return blocks
    def _recover_visuals(self, blocks: List[Block], pdf_path: Path, out: Path) -> List[Block]:
        """Rasterize the chapter opener and standalone figures from the print
        PDF and splice them into the block stream at their page positions."""
        extractor = PDFVisualExtractor(pdf_path, out / "images")
        if not extractor.available():
            self.emit("visuals", "PyMuPDF unavailable; skipping PDF visual recovery",
                      level=Level.WARNING)
            return blocks
        records = extractor.extract(want_figures=self.config.convert_assets)
        if not records:
            return blocks

        finisher_pages = {r.page_index: r.y0 for r in records if r.kind == "finisher"}
        if finisher_pages:
            # Keep the Exercise-6 answer text, but remove duplicate reconstructed
            # finisher headings and the standalone QR link. The exact source crop
            # becomes the sole final artwork.
            blocks = [
                b for b in blocks
                if not (
                    isinstance(b, ImageBlock)
                    and "qrcode" in (
                        (b.alt or "") + " " + (b.original_ref or "")
                    ).replace(" ", "").lower()
                )
                and not (
                    isinstance(b, TextBlock)
                    and re.search(
                        r"chapter complete|scan qr to challenge|make your own part test",
                        b.text or "", re.I,
                    )
                )
            ]

        new_blocks = list(blocks)
        openers = figures = finishers = 0

        def text_anchor_index(anchor: str, before: bool, source_page: int):
            target = self._pdf_norm(anchor)
            if len(target) < 12:
                return (None, 0.0)
            target = target[-1200:] if before else target[:1200]
            best_index, best_score = None, 0.0
            for index, candidate_block in enumerate(new_blocks):
                if not isinstance(candidate_block, TextBlock):
                    continue
                if candidate_block.page != source_page:
                    continue
                candidate = self._pdf_norm(candidate_block.text)
                if len(candidate) < 8:
                    continue
                if candidate[:35] and candidate[:35] in target:
                    score = 1.0 + min(len(candidate), 200) / 1000.0
                elif target[:35] and target[:35] in candidate:
                    score = 0.95
                else:
                    probe = candidate[:180]
                    score = SequenceMatcher(None, probe, target[-220:] if before else target[:220]).ratio()
                if score > best_score:
                    best_index, best_score = index, score
            return ((best_index, best_score) if best_score >= 0.42
                    else (None, best_score))

        for rec in records:
            img = ImageBlock(src=rec.rel_path, original_ref=f"pdf:p{rec.page_index}")
            img.page = rec.page_index
            img.y = rec.y0
            img.width = rec.width_px
            img.height = rec.height_px
            if rec.kind == "opener":
                img.alt = "chapter opener"
                new_blocks.insert(0, img)
                openers += 1
                continue
            if rec.kind == "finisher":
                img.alt = "chapter finisher"
                finishers += 1
                new_blocks.append(img)
                continue
            else:
                img.alt = "figure"
                figures += 1

            # Replace a nearby unresolved placed-art frame with the recovered
            # source crop rather than leaving a duplicate missing placeholder.
            nearby = [
                (abs(float(getattr(b, "y", 0)) - rec.y0), i)
                for i, b in enumerate(new_blocks)
                if isinstance(b, ImageBlock) and not b.src and b.page == rec.page_index
            ]
            if nearby and min(nearby)[0] < 100:
                new_blocks.pop(min(nearby)[1])

            # Diagram-bearing matching tables contain intentionally empty text
            # cells whose source content is EPS artwork. Keep recovered chemical
            # structures adjacent to that table instead of drifting elsewhere.
            table_targets = []
            for ti, tb in enumerate(new_blocks):
                if not isinstance(tb, TableBlock) or tb.page != rec.page_index:
                    continue
                empties = sum(1 for row in tb.rows for cell in row
                              if not str(cell.get("text", "")).strip())
                if empties >= 2 and abs(float(tb.y) - rec.y0) < 260:
                    table_targets.append((abs(float(tb.y) - rec.y0), ti))
            if table_targets:
                new_blocks.insert(min(table_targets)[1], img)
                continue

            # Prefer semantic source anchors over page-only placement.
            before_index, before_score = text_anchor_index(
                rec.anchor_before, before=True, source_page=rec.page_index
            )
            after_index, after_score = text_anchor_index(
                rec.anchor_after, before=False, source_page=rec.page_index
            )
            # A substantial preceding paragraph is a more reliable figure
            # anchor than short labels detected inside the artwork below it.
            # This keeps graphs after their source explanation instead of
            # jumping them directly under the section heading.
            if before_index is not None and (
                    len(self._pdf_norm(rec.anchor_before)) >= 120
                    or before_score >= 0.55
                    or before_score >= after_score
            ):
                insert_at = before_index + 1
            elif after_index is not None:
                insert_at = after_index
            else:
                same_page = [i for i, b in enumerate(new_blocks) if b.page == rec.page_index]
                later = [
                    i for i in same_page
                    if float(getattr(new_blocks[i], "y", 0)) >= rec.y0
                ]
                if later:
                    insert_at = min(later)
                elif same_page:
                    insert_at = max(same_page) + 1
                else:
                    later_pages = [
                        i for i, b in enumerate(new_blocks) if b.page > rec.page_index
                    ]
                    insert_at = min(later_pages) if later_pages else len(new_blocks)
            new_blocks.insert(insert_at, img)
        self.emit(
            "visuals",
            f"Recovered {openers} opener + {figures} inline figures + "
            f"{finishers} chapter finisher from print PDF",
            progress=1.0,
        )
        return new_blocks
    def _image_block(self, frame: Frame, repo: AssetRepository):
        if not self.config.convert_assets:
            return None
        record = repo.resolve(frame.link_uri)
        src = record.output_rel if record.found and record.output_rel else ""
        block = self.adapter.image_frame_to_block(frame, src=src, original_ref=frame.link_uri)
        block.alt = record.original_name
        if not src:
            self.emit(
                "assets",
                f"Could not place image: {record.original_name} ({record.note})",
                level=Level.WARNING,
            )
        return block

    def _merge_anchored_runs(self, blocks: List[Block]) -> List[Block]:
        """One visual callout box in the source is often split across several
        anchored frames (content, then a 'Key Note' label, then more content).
        Merge each maximal run of consecutive anchored blocks into a single box
        and hoist its callout label to the top, so the label sits above its box
        instead of between fragments."""
        out: List[Block] = []
        bgc = max((getattr(b, "box_group", 0) for b in blocks), default=0)
        i, n = 0, len(blocks)
        while i < n:
            if not getattr(blocks[i], "anchored", False):
                out.append(blocks[i])
                i += 1
                continue
            j = i
            while j < n and getattr(blocks[j], "anchored", False):
                j += 1
            run = blocks[i:j]
            bgc += 1
            for b in run:
                b.box_group = bgc
                b.box_kind = "callout"
            labels = [b for b in run if self._is_callout_label(b)]
            others = [b for b in run if not self._is_callout_label(b)]
            out.extend(labels + others)
            i = j
        return out

    @staticmethod
    def _is_callout_label(block: Block) -> bool:
        if not isinstance(block, TextBlock):
            return False
        t = block.text.strip()
        return len(t) <= 24 and bool(
            _CALLOUT_LABEL_RE.search(t) or _EX_LABEL_RE.search(t)
        )

    @staticmethod
    def _is_ex_label(block: Block) -> bool:
        if not isinstance(block, TextBlock):
            return False
        t = block.text.strip()
        return len(t) <= 24 and bool(_EX_LABEL_RE.search(t))

    def _group_examples(self, blocks: List[Block]) -> List[Block]:
        """Wrap each worked example in its own box. An 'Ex-N' ribbon marks the
        example: the block just before it is the question, and the blocks after
        it (Sol./working) belong to the same box, up to the next example, a
        heading, a question-section bar, or a Key Note box."""
        from idml2mobile.render.html_renderer import _QSECTION_RE

        ex_idx = [k for k, b in enumerate(blocks) if self._is_ex_label(b)]
        if not ex_idx:
            return blocks
        base = max((getattr(b, "box_group", 0) for b in blocks), default=0)
        heading_types = {BlockType.CHAPTER_TITLE, BlockType.HEADING, BlockType.SUBHEADING}

        def is_boundary(b: Block) -> bool:
            if self._is_ex_label(b):
                return True
            if isinstance(b, TextBlock):
                if b.type in heading_types:
                    return True
                if _QSECTION_RE.search(b.text or ""):
                    return True
            return getattr(b, "box_kind", "") == "callout"

        def is_solution(b: Block) -> bool:
            if not isinstance(b, TextBlock):
                return False
            return (b.type == BlockType.SOLUTION
                    or bool(re.match(r"^\s*sol\b", b.text or "", re.I)))

        def is_question(b: Block) -> bool:
            if not isinstance(b, TextBlock) or is_solution(b):
                return False
            return b.type in (BlockType.QUESTION, BlockType.PARAGRAPH)

        for n, i in enumerate(ex_idx):
            eid = base + n + 1
            rib = blocks[i]
            rib.ex_label = True
            rib.box_group = eid
            rib.box_kind = "example"
            rib.anchored = False
            # the question immediately before the ribbon joins this box (a
            # solution before the ribbon belongs to the PREVIOUS example instead)
            j = i - 1
            if (j >= 0 and is_question(blocks[j])
                    and getattr(blocks[j], "box_kind", "") not in ("callout", "example")):
                blocks[j].box_group = eid
                blocks[j].box_kind = "example"
            # following blocks (solution/working) join this box, up to the next
            # example; reserve the next example's own preceding question for it.
            nxt = ex_idx[n + 1] if n + 1 < len(ex_idx) else len(blocks)
            end = nxt
            if nxt < len(blocks) and is_question(blocks[nxt - 1]):
                end = nxt - 1
            k = i + 1
            while k < end:
                c = blocks[k]
                if is_boundary(c):
                    break
                c.box_group = eid
                c.box_kind = "example"
                k += 1
        # Hoist each ribbon to the beginning of its example box.
        ordered: List[Block] = []
        i = 0
        while i < len(blocks):
            group = getattr(blocks[i], "box_group", 0)
            kind = getattr(blocks[i], "box_kind", "")
            if not group or kind != "example":
                ordered.append(blocks[i])
                i += 1
                continue
            j = i
            while j < len(blocks) and getattr(blocks[j], "box_group", 0) == group:
                j += 1
            run = blocks[i:j]
            ordered.extend([b for b in run if getattr(b, "ex_label", False)])
            ordered.extend([b for b in run if not getattr(b, "ex_label", False)])
            i = j
        return ordered

    @staticmethod
    def _hoist_question_headers(blocks: List[Block]) -> List[Block]:
        """Move a trailing Check Your Understanding label above its questions."""
        out = list(blocks)
        i = 0
        while i < len(out):
            block = out[i]
            is_header = (
                isinstance(block, TextBlock)
                and bool(re.search(r"check\s*your\s*understanding", block.text, re.I))
            )
            if not is_header:
                i += 1
                continue
            start = i
            while start > 0:
                prev = out[start - 1]
                if not isinstance(prev, TextBlock):
                    break
                if prev.type not in (BlockType.QUESTION, BlockType.OPTION):
                    break
                if getattr(prev, "box_kind", "") == "example":
                    break
                start -= 1
            if start < i:
                header = out.pop(i)
                out.insert(start, header)
                i = start
            # Keep the header and its question run in one source-style box.
            group = max((getattr(b, "box_group", 0) for b in out), default=0) + 1
            out[i].box_group = group
            out[i].box_kind = "questions"
            j = i + 1
            while j < len(out):
                item = out[j]
                if not isinstance(item, TextBlock):
                    break
                if item.type not in (BlockType.QUESTION, BlockType.OPTION):
                    break
                item.box_group = group
                item.box_kind = "questions"
                j += 1
            i = max(i + 1, j)
        return out

    def _coverage(self, stories: Dict[str, RawStory], document: Document) -> dict:
        """Structural coverage: how many source elements made it into the output."""
        src_tables = src_images = src_textframes = 0
        for st in stories.values():
            for para in st.paragraphs:
                for r in para.runs:
                    if r.table:
                        src_tables += 1
                    if r.image_uri:
                        src_images += 1
                    if r.textframe_story:
                        src_textframes += 1

        out_tables = out_eq_total = out_eq_placed = out_figs = out_boxes = 0
        seen_boxes = set()
        for node in document.walk():
            if isinstance(node, TableBlock):
                out_tables += 1
            elif isinstance(node, ImageBlock):
                if str(node.original_ref).startswith("pdf:"):
                    out_figs += 1
            elif isinstance(node, TextBlock):
                for r in node.runs:
                    if (r.is_image and
                            (r.original_ref or "").lower().endswith((".wmf", ".emf"))):
                        out_eq_total += 1
                        if r.src or r.latex:
                            out_eq_placed += 1
                if node.box_group:
                    seen_boxes.add(node.box_group)
        out_boxes = len(seen_boxes)

        def pct(a, b):
            return round(100.0 * a / b, 1) if b else 100.0

        return {
            "tables": {"source": src_tables, "rendered": out_tables,
                       "match_pct": pct(out_tables, src_tables)},
            "equations_anchored": {
                "in_output": out_eq_total,
                "editable_or_fallback_resolved": out_eq_placed,
                "resolved_pct": pct(out_eq_placed, out_eq_total),
            },
            "diagrams_recovered_from_pdf": out_figs,
            "callout_boxes": out_boxes,
            "source_anchored_frames": src_textframes,
            "note": ("Reflow is a re-layout, so per-page pixel match is N/A; these "
                     "are structural content-coverage counts (source vs output)."),
        }

    def _build_document(self, blocks: List[Block], validation: ValidationResult) -> Document:
        title = self._guess_title(blocks, validation.idml_file.stem)
        builder = DocumentBuilder(title=title)
        builder.set_meta(source=str(validation.idml_file))
        return builder.add_blocks(blocks).build()

    @staticmethod
    def _guess_title(blocks: List[Block], stem: str) -> str:
        import re as _re
        key = _re.sub(r"^[\d_\-\s]+", "", stem).replace("_", " ").strip().lower()
        keyset = {key, key + "s", key.rstrip("s"), key.rstrip("s") + "s"} - {""}

        headings = [
            b for b in blocks
            if isinstance(b, TextBlock) and b.type.value in ("chapter_title", "heading")
        ]
        # 1. a short heading whose text matches the filename keyword (the chapter
        #    name, e.g. file "01_Solution" -> block "SOLUTIONS"). Prefer an
        #    explicit chapter_title, then the first match.
        matches = [b for b in headings
                   if b.text.strip().lower() in keyset and len(b.text.strip()) <= 20]
        for b in matches:
            if b.type.value == "chapter_title":
                return b.text.strip()
        if matches:
            return matches[0].text.strip()
        # 2. any explicit, short chapter_title block
        for b in headings:
            if b.type.value == "chapter_title" and len(b.text.strip()) <= 40:
                return b.text.strip()
        # 3. derive from the file name
        return key.title() if key else (stem or "Document")

    # -- stats -------------------------------------------------------------
    def _compute_stats(self, document: Document, asset_records, elapsed: float,
                       source_pages: int = 0) -> dict:
        chars = 0
        words = 0
        text_blocks = 0
        equations = 0
        tables = 0
        for node in document.walk():
            if isinstance(node, TableBlock):
                tables += 1
            elif isinstance(node, TextBlock):
                text_blocks += 1
                t = node.text
                chars += len(t)
                words += len(t.split())
                equations += sum(1 for r in node.runs if r.is_image)
        # No LLM is involved in conversion; this is an estimate of the volume of
        # text processed, using the common ~4-chars-per-token heuristic.
        tokens_est = math.ceil(chars / 4) if chars else 0
        linked_images = sum(1 for r in asset_records if getattr(r, "found", False)
                            and getattr(r, "output_rel", ""))
        recovered_figures = sum(1 for node in document.walk()
                                if isinstance(node, ImageBlock) and getattr(node, "src", ""))
        inline_assets = sum(1 for node in document.walk()
                            if isinstance(node, TextBlock)
                            for run in node.runs
                            if getattr(run, "is_image", False) and (getattr(run, "src", "") or getattr(run, "latex", "")))
        images_placed = max(linked_images, recovered_figures) + inline_assets
        pages = source_pages or len(
            {node.page for node in document.walk() if isinstance(node, Block)}
        )
        return {
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_human": self._fmt_duration(elapsed),
            "text_tokens_est": tokens_est,
            "words": words,
            "characters": chars,
            "text_blocks": text_blocks,
            "sections": len(document.sections),
            "equations": equations,
            "tables": tables,
            "images_placed": images_placed,
            "assets_total": len(asset_records),
            "pages": pages,
            "token_estimate_note": "estimate only - conversion is offline, no LLM tokens are used",
        }

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}s"
        m, s = divmod(int(round(seconds)), 60)
        return f"{m}m {s:02d}s"

    def _write_stats(self, out: Path, stats: dict) -> None:
        (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    # -- output ------------------------------------------------------------
    def _write_html_and_assets(self, document, out: Path, validation) -> Path:
        css_dir = out / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        faces = self._copy_fonts(out, validation)
        css = StyleBuilder(self.profile).with_fonts(faces).build()
        (css_dir / "styles.css").write_text(css, encoding="utf-8")
        self._copy_katex(out)

        renderer = HTMLRenderer(self.profile, css_href="css/styles.css", katex_local=True)
        html = renderer.render(document)
        index = out / "index.html"
        index.write_text(html, encoding="utf-8")
        return index

    def _copy_katex(self, out: Path) -> None:
        """Copy the vendored KaTeX (CSS/JS + woff2 fonts) into output/katex so the
        page renders LaTeX offline and the PDF is self-contained."""
        src = Path(__file__).resolve().parent / "resources" / "katex"
        if not src.exists():
            return
        dest = out / "katex"
        (dest / "fonts").mkdir(parents=True, exist_ok=True)
        (out / "css").mkdir(parents=True, exist_ok=True)
        (out / "js").mkdir(parents=True, exist_ok=True)
        for f in src.glob("*.*"):
            shutil.copy2(f, dest / f.name)
            if f.name == "katex.min.css":
                shutil.copy2(f, out / "css" / f.name)
            elif f.suffix.lower() == ".js":
                shutil.copy2(f, out / "js" / f.name)
        for f in (src / "fonts").glob("*.woff2"):
            shutil.copy2(f, dest / "fonts" / f.name)

    def _copy_fonts(self, out: Path, validation) -> List:
        faces: List = []
        if not (self.config.embed_fonts and validation.fonts_dir):
            return faces
        fonts_out = out / "fonts"
        fonts_out.mkdir(parents=True, exist_ok=True)
        sources = [f for f in sorted(validation.fonts_dir.glob("*"))
                   if f.suffix.lower() in _FONT_EXT]
        for src in sources:
            shutil.copy2(src, fonts_out / src.name)
            low = src.stem.lower()
            weight = "700" if any(x in low for x in ("bold", "black", "blk")) else "normal"
            style = "italic" if any(x in low for x in ("italic", "oblique")) else "normal"
            faces.append((src.stem, f"fonts/{src.name}", weight, style))
        def alias(family, predicate, weight="normal", style="normal"):
            hit = next((f for f in sources if predicate(f.stem.lower())), None)
            if hit:
                faces.append((family, f"fonts/{hit.name}", weight, style))
        alias("BodySerif", lambda n: "minionpro-regular" in n or n == "times")
        alias("BodySerif", lambda n: "minion" in n and "bold" in n or n == "timesbd", "700")
        alias("BodySerif", lambda n: "minion" in n and "italic" in n or n == "timesi", "normal", "italic")
        alias("HeadingSans", lambda n: "graphik-regular" in n or n == "helvetica_0")
        alias("HeadingSans", lambda n: "graphik-bold" in n or "graphik-black" in n, "700")
        return faces

    def _render_pdf(self, html_path: Path, out: Path) -> Optional[Path]:
        self.emit("render-pdf", "Rendering PDF with Playwright Chromium", progress=0.2)
        try:
            pdf = PDFRenderer(self.profile).render(html_path, out / "mobile.pdf")
            self.emit("render-pdf", f"Wrote {pdf.name}", progress=1.0)
            return pdf
        except PlaywrightNotInstalled as exc:
            self.emit("render-pdf", str(exc), level=Level.ERROR)
            return None






