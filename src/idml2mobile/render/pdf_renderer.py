"""PDFRenderer — rasterizes the mobile HTML to PDF with Playwright Chromium.

Uses the narrow mobile viewport, waits for KaTeX to typeset, and prints with
`preferCSSPageSize` so the @page 360px-wide rule from the stylesheet drives the
page geometry. Background printing is on so callout tints survive.
"""
from __future__ import annotations

from pathlib import Path

from idml2mobile.config import MobileProfile


class PlaywrightNotInstalled(RuntimeError):
    pass


class PDFRenderer:
    def __init__(self, profile: MobileProfile) -> None:
        self.profile = profile

    def render(self, html_path: Path, pdf_path: Path, wait_math: bool = True) -> Path:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise PlaywrightNotInstalled(
                "playwright is required for PDF rendering. Install with:\n"
                "  pip install playwright && playwright install chromium"
            ) from exc

        html_path = Path(html_path).resolve()
        pdf_path = Path(pdf_path).resolve()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        p = self.profile

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width": p.page_width, "height": p.page_height},
                device_scale_factor=2,
            )
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="networkidle", timeout=60_000)
            if wait_math:
                # Give KaTeX auto-render a beat; ignore if it never appears.
                try:
                    page.wait_for_function(
                        "document.fonts.ready.then(()=>true)", timeout=8_000
                    )
                except Exception:
                    pass
                page.wait_for_timeout(400)

            pdf_kwargs = {
                "path": str(pdf_path),
                "print_background": True,
                "prefer_css_page_size": True,
                "margin": {"top": "0", "bottom": "0", "left": "0", "right": "0"},
            }
            if not p.paginated:
                pdf_kwargs["width"] = f"{p.width_in:.4f}in"
                pdf_kwargs["height"] = f"{p.height_in:.4f}in"
                pdf_kwargs["prefer_css_page_size"] = False
            else:
                pdf_kwargs["width"] = f"{p.width_in:.4f}in"

            page.pdf(**pdf_kwargs)
            context.close()
            browser.close()
        return pdf_path
