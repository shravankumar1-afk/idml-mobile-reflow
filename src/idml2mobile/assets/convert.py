"""Convert unsupported source assets to web-safe PNG.

Strategy per format:
  * PNG/JPG/JPEG/GIF/WebP -> copied as-is.
  * TIF/TIFF/BMP          -> re-encoded to PNG via Pillow.
  * WMF/EMF               -> rasterized via Pillow (Windows GDI) with upscaling;
                            on non-Windows, falls back to ImageMagick/Inkscape.
  * EPS                   -> rasterized via Pillow (needs Ghostscript on PATH),
                            else ImageMagick/Inkscape.
  * CDR/AI/SVG            -> ImageMagick/Inkscape if present; else reported
                            unconverted (never cropped).
Never crops: conversion preserves the full artwork bounding box.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

RASTER_OK = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
# WMF/EMF render through the Windows metafile decoder Pillow ships on win32.
PILLOW_CONVERT = {".tif", ".tiff", ".bmp", ".eps", ".wmf", ".emf"}
VECTOR_EXTERNAL = {".cdr", ".svg", ".ai", ".pdf"}
# Rasterize vector metafiles at this DPI (crisp equations); cap the pixel size.
_WMF_DPI = 600
_MAX_EQ_PX = 1600


@dataclass
class ConversionOutcome:
    ok: bool
    output_path: Optional[Path]
    method: str
    note: str = ""


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def convert_to_websafe(src: Path, out_dir: Path, stem: str) -> ConversionOutcome:
    src = Path(src)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()

    if ext in RASTER_OK:
        dest = out_dir / f"{stem}{ext}"
        shutil.copy2(src, dest)
        return ConversionOutcome(True, dest, "copy")

    if ext in PILLOW_CONVERT:
        outcome = _pillow_convert(src, out_dir / f"{stem}.png")
        if outcome.ok:
            return outcome
        # fall through to external tools for EPS/metafiles if Pillow failed
        return _external_convert(src, out_dir / f"{stem}.png", prior=outcome.note)

    if ext in VECTOR_EXTERNAL:
        return _external_convert(src, out_dir / f"{stem}.png")

    return ConversionOutcome(False, None, "unsupported", f"Unhandled format: {ext}")


def _pillow_convert(src: Path, dest: Path) -> ConversionOutcome:
    ext = src.suffix.lower()
    try:
        from PIL import Image  # noqa: WPS433 (local import keeps import time low)

        with Image.open(src) as im:
            if ext == ".eps":
                im.load(scale=4)
            elif ext in (".wmf", ".emf"):
                # Metafiles are VECTOR: rasterize at high DPI so equations are
                # crisp. (Loading native then upscaling produced blurry output.)
                im.load(dpi=_WMF_DPI)
            else:
                im.load()
            # Bound the largest side so a big equation doesn't create a huge PNG.
            longest = max(im.size) if im.size else 0
            if longest > _MAX_EQ_PX:
                f = _MAX_EQ_PX / longest
                im = im.resize((max(1, int(im.size[0] * f)), max(1, int(im.size[1] * f))),
                               Image.LANCZOS)
            if im.mode in ("CMYK", "P", "LA"):
                im = im.convert("RGBA" if "A" in im.mode else "RGB")
            im.save(dest, "PNG")
        return ConversionOutcome(True, dest, "pillow")
    except Exception as exc:  # pragma: no cover - depends on system codecs
        return ConversionOutcome(False, None, "pillow", f"{type(exc).__name__}: {exc}")


def _external_convert(src: Path, dest: Path, prior: str = "") -> ConversionOutcome:
    # NOTE: never resolve bare `convert` on Windows -- that is the OS disk tool,
    # not ImageMagick. Only trust `magick`.
    magick = _which("magick")
    if magick is None and sys.platform != "win32":
        magick = _which("convert")
    if magick:
        try:
            subprocess.run(
                [magick, "-density", "220", str(src), "-background", "white",
                 "-flatten", str(dest)],
                check=True, capture_output=True, timeout=120,
            )
            if dest.exists():
                return ConversionOutcome(True, dest, "imagemagick")
        except Exception as exc:  # pragma: no cover
            last = f"imagemagick: {exc}"
        else:
            last = "imagemagick produced no file"
    else:
        last = "imagemagick not found"

    inkscape = _which("inkscape")
    if inkscape:
        try:
            subprocess.run(
                [inkscape, str(src), "--export-type=png",
                 f"--export-filename={dest}", "--export-dpi=220"],
                check=True, capture_output=True, timeout=120,
            )
            if dest.exists():
                return ConversionOutcome(True, dest, "inkscape")
        except Exception as exc:  # pragma: no cover
            last = f"inkscape: {exc}"

    detail = f"No converter succeeded ({last})."
    if prior:
        detail = f"Pillow: {prior}; " + detail
    if src.suffix.lower() == ".eps":
        detail += " EPS needs Ghostscript; WMF/EMF need Windows or ImageMagick."
    else:
        detail += " Install ImageMagick or Inkscape."
    return ConversionOutcome(False, None, "external", detail)
