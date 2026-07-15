"""Central configuration objects.

`MobileProfile` encodes the mobile-safe PDF page spec. `ConversionConfig`
bundles everything the pipeline needs for one run, so no module reaches for
global state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class MobileProfile:
    """Mobile-safe page geometry (all values in CSS px unless noted)."""

    page_width: int = 360
    page_height: int = 780          # fixed page; set paginated=True for auto height
    paginated: bool = True          # True -> flow content, let print engine paginate
    margin: int = 16
    body_font_px: int = 15
    min_font_px: int = 13
    line_height: float = 1.5
    css_dpi: int = 96               # CSS reference px per inch

    @property
    def safe_content_width(self) -> int:
        return self.page_width - 2 * self.margin  # 360 - 32 = 328

    @property
    def width_in(self) -> float:
        return self.page_width / self.css_dpi

    @property
    def height_in(self) -> float:
        return self.page_height / self.css_dpi


@dataclass
class ConversionConfig:
    """One conversion run's inputs and knobs."""

    input_path: Path
    output_dir: Path
    profile: MobileProfile = field(default_factory=MobileProfile)

    mode: str = "reflow"                   # source-faithful | reflow | facsimile(alias)
    reading_order_strategy: str = "auto"   # auto | threaded | geometric | story_order
    embed_fonts: bool = True
    convert_assets: bool = True
    recover_visuals: bool = True           # rasterize opener/figures from the print PDF
    render_pdf: bool = True
    reference_pdf: Optional[Path] = None
    keep_temp: bool = False
    verbose: bool = False
    # Optional override for the MathType-basename -> LaTeX map. When None the
    # bundled resources/equations.json is used.
    equations_path: Optional[Path] = None

    def __post_init__(self) -> None:
        self.input_path = Path(self.input_path)
        self.output_dir = Path(self.output_dir)
        if self.reference_pdf is not None:
            self.reference_pdf = Path(self.reference_pdf)
        if self.equations_path is not None:
            self.equations_path = Path(self.equations_path)
