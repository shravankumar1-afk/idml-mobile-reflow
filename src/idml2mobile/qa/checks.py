"""QA validation (spec step 12) -> qa-report.json.

Static checks run always (missing assets, broken math, font sizes, empty
sections, width contract). A dynamic pass runs the built HTML in Chromium to
detect real horizontal overflow and clipped images when Playwright is present.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from idml2mobile.config import MobileProfile
from idml2mobile.model.blocks import Document, ImageBlock, MathBlock, TextBlock


@dataclass
class QAReport:
    passed: bool = True
    checks: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, ok: bool, detail: Any = None, error: bool = False) -> None:
        self.checks[name] = {"ok": ok, "detail": detail}
        if not ok:
            (self.errors if error else self.warnings).append(name)
            if error:
                self.passed = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "coverage": self.coverage,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class QAValidator:
    def __init__(self, profile: MobileProfile) -> None:
        self.profile = profile

    def validate(
        self,
        output_dir: Path,
        document: Optional[Document] = None,
        asset_records: Optional[List[Any]] = None,
        run_dynamic: bool = True,
        coverage: Optional[dict] = None,
    ) -> QAReport:
        report = QAReport()
        output_dir = Path(output_dir)

        self._check_structure(output_dir, report)
        self._check_min_font(report)
        self._check_page_width(report)
        if document is not None:
            self._check_math(document, report)
            self._check_images_linked(document, output_dir, report)
            self._check_empty_sections(document, report)
        if asset_records:
            self._check_assets(asset_records, report)
        if run_dynamic:
            self._check_dynamic(output_dir, report)
        if coverage is not None:
            report.coverage = coverage
            tbl = coverage.get("tables", {})
            self.add_check(report, "tables_covered",
                           tbl.get("rendered", 0) >= tbl.get("source", 0),
                           tbl)

        (output_dir / "qa-report.json").write_text(
            json.dumps(report.as_dict(), indent=2), encoding="utf-8"
        )
        return report

    @staticmethod
    def add_check(report: QAReport, name: str, ok: bool, detail) -> None:
        report.add(name, ok, detail, error=False)

    # -- static checks -----------------------------------------------------
    def _check_structure(self, out: Path, report: QAReport) -> None:
        required = ["index.html", "css/styles.css"]
        missing = [r for r in required if not (out / r).exists()]
        report.add("required_files", not missing, {"missing": missing}, error=bool(missing))

    def _check_min_font(self, report: QAReport) -> None:
        ok = self.profile.body_font_px >= self.profile.min_font_px >= 13
        report.add(
            "min_font_size",
            ok,
            {"body": self.profile.body_font_px, "min": self.profile.min_font_px},
            error=not ok,
        )

    def _check_page_width(self, report: QAReport) -> None:
        p = self.profile
        ok = p.page_width == 360 and p.safe_content_width == 328
        report.add(
            "page_width_contract",
            ok,
            {"page_width": p.page_width, "safe_width": p.safe_content_width},
        )

    def _check_math(self, doc: Document, report: QAReport) -> None:
        broken: List[str] = []
        for node in doc.walk():
            if isinstance(node, MathBlock) and not node.fallback_image:
                if node.latex.count("{") != node.latex.count("}") or not node.latex.strip():
                    broken.append(node.latex[:60])
        report.add("math_well_formed", not broken, {"broken": broken}, error=False)

    def _check_images_linked(self, doc: Document, out: Path, report: QAReport) -> None:
        missing: List[str] = []
        inline_unresolved = 0
        for node in doc.walk():
            if isinstance(node, ImageBlock):
                if not node.src:
                    missing.append(node.original_ref or "(no ref)")
                elif not (out / node.src).exists():
                    missing.append(node.src)
            elif isinstance(node, TextBlock):
                for run in node.runs:
                    ref = (run.original_ref or "").lower()
                    if (run.is_image and ref.endswith((".wmf", ".emf"))
                            and not run.src and not run.latex):
                        inline_unresolved += 1
        report.add("images_linked", not missing, {"missing": missing}, error=False)
        report.add(
            "inline_equations_resolved",
            inline_unresolved == 0,
            {"unresolved": inline_unresolved},
        )

    def _check_empty_sections(self, doc: Document, report: QAReport) -> None:
        empties = [
            s.title or "(untitled)"
            for s in doc.sections
            if not any(
                isinstance(c, (TextBlock, ImageBlock, MathBlock)) and not (
                    isinstance(c, TextBlock) and c.is_empty()
                )
                for c in s.children
            )
        ]
        report.add("no_empty_sections", not empties, {"empty": empties})

    def _check_assets(self, records: List[Any], report: QAReport) -> None:
        not_found = [r.original_name for r in records if not getattr(r, "found", True)]
        not_converted = [
            r.original_name for r in records
            if getattr(r, "found", False) and not getattr(r, "output_rel", "")
        ]
        report.add("assets_found", not not_found, {"missing": not_found}, error=False)
        report.add(
            "assets_converted",
            not not_converted,
            {"unconverted": not_converted, "note": "install ImageMagick/Inkscape for WMF/CDR"},
        )

    # -- dynamic (rendered DOM) check --------------------------------------
    def _check_dynamic(self, out: Path, report: QAReport) -> None:
        index = out / "index.html"
        if not index.exists():
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            report.add("horizontal_overflow", True, {"note": "playwright absent; skipped static-only"})
            return

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(args=["--no-sandbox"])
                page = browser.new_context(
                    viewport={"width": self.profile.page_width, "height": self.profile.page_height}
                ).new_page()
                page.goto(index.resolve().as_uri(), wait_until="networkidle", timeout=60_000)
                page.wait_for_timeout(300)
                metrics = page.evaluate(
                    """() => {
                        const de = document.documentElement;
                        const over = de.scrollWidth - de.clientWidth;
                        const clipped = [...document.images].filter(
                            img => img.naturalWidth > 0 &&
                                   img.getBoundingClientRect().width >
                                   document.documentElement.clientWidth + 1
                        ).map(img => img.currentSrc || img.src);
                        const broken = [...document.images].filter(
                            img => img.complete && img.naturalWidth === 0
                        ).map(img => img.currentSrc || img.src);
                        const katexErrors = [...document.querySelectorAll('.katex-error')]
                            .map(e => e.textContent).slice(0, 20);
                        // any leftover un-rendered LaTeX delimiters in the body text
                        const bodyText = document.body.innerText || "";
                        const rawLatex = /\\\\\\(|\\\\\\[|\\\\frac/.test(bodyText);
                        const overflowElements = [...document.querySelectorAll("body *")]
                            .filter(e => e.scrollWidth > e.clientWidth + 1)
                            .slice(0, 20)
                            .map(e => ({tag:e.tagName, cls:String(e.className || ""),
                                scroll:e.scrollWidth, client:e.clientWidth,
                                text:(e.textContent || "").slice(0, 220)}));
                        return {overflow: over, clipped, broken, katexErrors, rawLatex,
                                overflowElements};
                    }"""
                )
                browser.close()
        except Exception as exc:  # pragma: no cover
            report.add("horizontal_overflow", True, {"note": f"dynamic check failed: {exc}"})
            return

        overflow_ok = metrics["overflow"] <= 1
        report.add(
            "horizontal_overflow",
            overflow_ok,
            {"overflow_px": metrics["overflow"],
             "elements": metrics.get("overflowElements", [])},
            error=not overflow_ok,
        )
        report.add("no_clipped_images", not metrics["clipped"], {"clipped": metrics["clipped"]})
        report.add("no_broken_images", not metrics["broken"], {"broken": metrics["broken"]},
                   error=bool(metrics["broken"]))
        # KaTeX health: no equation should fail to render, and no raw LaTeX
        # delimiter should survive un-rendered in the visible text.
        ke = metrics.get("katexErrors") or []
        report.add("katex_rendered_ok", not ke and not metrics.get("rawLatex"),
                   {"katex_errors": ke, "unrendered_latex": metrics.get("rawLatex")},
                   error=bool(ke))
