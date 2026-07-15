"""Click-based CLI. Thin layer: parse args -> build Command -> execute."""
from __future__ import annotations

import sys
from pathlib import Path

import click

from idml2mobile.commands import (
    BatchCommand,
    ConvertCommand,
    InspectCommand,
    ValidateCommand,
)
from idml2mobile.config import ConversionConfig, MobileProfile
from idml2mobile.observers.progress import RichProgressObserver

STRATEGIES = ["auto", "threaded", "geometric", "story_order"]


def _profile(page_width, page_height, paginated, body_font, min_font, margin) -> MobileProfile:
    return MobileProfile(
        page_width=page_width,
        page_height=page_height,
        paginated=paginated,
        margin=margin,
        body_font_px=body_font,
        min_font_px=min_font,
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="idml2mobile")
def cli() -> None:
    """Convert double-column IDML packages into single-column mobile PDFs."""


# -- shared profile options ------------------------------------------------
def profile_options(f):
    f = click.option("--page-width", default=360, show_default=True, type=int)(f)
    f = click.option("--page-height", default=780, show_default=True, type=int)(f)
    f = click.option("--paginated/--fixed-height", default=True, show_default=True)(f)
    f = click.option("--body-font", default=15, show_default=True, type=int)(f)
    f = click.option("--min-font", default=13, show_default=True, type=int)(f)
    f = click.option("--margin", default=16, show_default=True, type=int)(f)
    return f


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "output_dir", required=True, type=click.Path(path_type=Path))
@click.option("--mode", type=click.Choice(["source-faithful", "reflow", "facsimile"]),
              default="reflow", show_default=True,
              help="source-faithful/facsimile = 100% visual preservation; "
                   "reflow = editable single-column reconstruction.")
@click.option("--strategy", type=click.Choice(STRATEGIES), default="auto", show_default=True)
@click.option("--no-pdf", is_flag=True, help="Skip Playwright PDF rendering.")
@click.option("--no-fonts", is_flag=True, help="Do not embed Document fonts.")
@click.option("--no-visuals", is_flag=True,
              help="Do not recover the chapter opener/figures from the reference PDF.")
@click.option("--keep-temp", is_flag=True, help="Keep the unpacked IDML temp dir.")
@click.option("-v", "--verbose", is_flag=True)
@profile_options
def convert(input_path, output_dir, mode, strategy, no_pdf, no_fonts, no_visuals, keep_temp,
            verbose, page_width, page_height, paginated, body_font, min_font, margin):
    """Convert INPUT_PATH (an .idml file or a package folder) to mobile output."""
    config = ConversionConfig(
        input_path=input_path,
        output_dir=output_dir,
        mode=mode,
        profile=_profile(page_width, page_height, paginated, body_font, min_font, margin),
        reading_order_strategy=strategy,
        embed_fonts=not no_fonts,
        recover_visuals=not no_visuals,
        render_pdf=not no_pdf,
        keep_temp=keep_temp,
        verbose=verbose,
    )
    cmd = ConvertCommand(config).attach_observer(RichProgressObserver(verbose=verbose))
    sys.exit(cmd.execute())


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def inspect(input_path, as_json):
    """Report structure/stats of an IDML package without converting."""
    sys.exit(InspectCommand(input_path, as_json=as_json).execute())


@cli.command()
@click.argument("output_dir", type=click.Path(exists=True, path_type=Path))
@profile_options
def validate(output_dir, page_width, page_height, paginated, body_font, min_font, margin):
    """Run QA checks against an existing OUTPUT_DIR."""
    profile = _profile(page_width, page_height, paginated, body_font, min_font, margin)
    sys.exit(ValidateCommand(output_dir, profile=profile).execute())


@cli.command()
@click.argument("input_root", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "output_root", required=True, type=click.Path(path_type=Path))
@click.option("--no-pdf", is_flag=True)
@profile_options
def batch(input_root, output_root, no_pdf, page_width, page_height, paginated,
          body_font, min_font, margin):
    """Convert every IDML package under INPUT_ROOT."""
    profile = _profile(page_width, page_height, paginated, body_font, min_font, margin)
    cmd = BatchCommand(input_root, output_root, profile=profile, render_pdf=not no_pdf)
    cmd.attach_observer(RichProgressObserver())
    sys.exit(cmd.execute())


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
