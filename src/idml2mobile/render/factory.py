"""RendererFactory — builds configured content/PDF renderers.

Keeps renderer construction (and their profile wiring) behind one seam, so the
pipeline asks for "html" or "pdf" and never imports concrete classes.
"""
from __future__ import annotations

from idml2mobile.config import MobileProfile
from idml2mobile.render.html_renderer import HTMLRenderer
from idml2mobile.render.pdf_renderer import PDFRenderer


class RendererFactory:
    def __init__(self, profile: MobileProfile) -> None:
        self.profile = profile

    def create(self, kind: str, **kw):
        kind = kind.lower()
        if kind == "html":
            return HTMLRenderer(self.profile, **kw)
        if kind == "pdf":
            return PDFRenderer(self.profile)
        raise ValueError(f"Unknown renderer kind: {kind}")
