import json

from idml2mobile.config import ConversionConfig, MobileProfile
from idml2mobile.model.blocks import BlockType, Document, InlineRun, Section, TextBlock
from idml2mobile.pipeline import ConversionPipeline
from idml2mobile.qa.checks import QAValidator


def test_profile_safe_width():
    p = MobileProfile()
    assert p.page_width == 360
    assert p.safe_content_width == 328
    assert p.min_font_px >= 13


def test_qa_flags_min_font_below_13(tmp_path):
    (tmp_path / "css").mkdir()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "css" / "styles.css").write_text("body{}", encoding="utf-8")
    profile = MobileProfile(body_font_px=10, min_font_px=10)
    report = QAValidator(profile).validate(tmp_path, run_dynamic=False)
    assert report.checks["min_font_size"]["ok"] is False
    assert not report.passed


def test_end_to_end_produces_outputs(sample_package, tmp_path):
    out = tmp_path / "out"
    config = ConversionConfig(
        input_path=sample_package, output_dir=out, render_pdf=False,
    )
    result = ConversionPipeline(config).convert()

    assert (out / "index.html").exists()
    assert (out / "css" / "styles.css").exists()
    assert (out / "qa-report.json").exists()

    # document structure
    assert result.document is not None
    titles = [s.title for s in result.document.sections]
    assert "Solutions" in titles

    # semantic classification reached the HTML (a question renders as
    # "question" when numbered, else "qcont"; the option as "option")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'class="question"' in html or 'class="qcont"' in html
    assert 'class="option"' in html

    # qa report is valid json with the width contract check
    report = json.loads((out / "qa-report.json").read_text(encoding="utf-8"))
    assert report["checks"]["page_width_contract"]["ok"] is True


def test_finds_idml_in_nested_subfolder(sample_package, tmp_path):
    # Wrap the package in an outer folder (the layout that used to fail).
    outer = tmp_path / "wrapper"
    outer.mkdir()
    import shutil
    shutil.move(str(sample_package), str(outer / "inner"))

    from idml2mobile.idml.validator import InputValidator
    result = InputValidator().validate(outer)
    assert result.ok
    assert result.idml_file is not None
    assert result.idml_file.name == "sample.idml"
    # base is anchored on the .idml's real parent, so Links/fonts resolve
    assert result.links_dir is not None
    assert result.fonts_dir is not None


def test_stats_reported(sample_package, tmp_path):
    out = tmp_path / "out"
    config = ConversionConfig(input_path=sample_package, output_dir=out, render_pdf=False)
    result = ConversionPipeline(config).convert()
    s = result.stats
    assert s["elapsed_seconds"] >= 0
    assert s["text_tokens_est"] > 0
    assert s["words"] > 0
    assert "elapsed_human" in s
    assert (out / "stats.json").exists()


def test_output_into_source_package_is_blocked(sample_package):
    import pytest
    # Output == the source package folder must be refused (protects source files).
    config = ConversionConfig(
        input_path=sample_package, output_dir=sample_package, render_pdf=False,
    )
    with pytest.raises(ValueError, match="source package"):
        ConversionPipeline(config).convert()
    # source .idml is untouched
    assert (sample_package / "sample.idml").exists()


def test_katex_vendored_and_wired(sample_package, tmp_path):
    """Equations render via a self-contained (vendored, no-CDN) KaTeX setup."""
    out = tmp_path / "out"
    ConversionPipeline(
        ConversionConfig(input_path=sample_package, output_dir=out, render_pdf=False)
    ).convert()
    html = (out / "index.html").read_text(encoding="utf-8")
    # local KaTeX is referenced (never a remote CDN) and auto-render is initialised
    assert 'href="katex/katex.min.css"' in html
    assert 'src="katex/katex.min.js"' in html
    assert "renderMathInElement" in html
    assert "cdn" not in html.lower()
    # vendored assets were copied into the output so the PDF is self-contained
    assert (out / "katex" / "katex.min.css").exists()
    assert (out / "katex" / "katex.min.js").exists()
    assert list((out / "katex" / "fonts").glob("*.woff2"))


def test_equation_map_attaches_latex():
    """A transcribed equation becomes a LaTeX run (KaTeX), not an image."""
    from idml2mobile.mathconv.equations import EquationMap

    em = EquationMap.load()
    hit = em.lookup("file:///C:/x/Eqn-JEE_M-437.wmf")
    assert hit is not None and "\\frac" in hit.latex


def test_pdf_visual_extractor_recovers_opener(tmp_path):
    import pytest
    fitz = pytest.importorskip("fitz")

    from idml2mobile.assets.pdf_visuals import PDFVisualExtractor

    pdf = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # a graphic band at the top, then a long body paragraph below it
    page.draw_rect(fitz.Rect(60, 40, 550, 300), color=(0, 0, 1), fill=(0.6, 0.8, 1))
    body = ("This is a long body paragraph of real running text that easily "
            "exceeds one hundred and twenty characters so it is treated as body.")
    page.insert_textbox(fitz.Rect(60, 360, 550, 700), body, fontsize=12)
    doc.save(str(pdf))
    doc.close()

    images = tmp_path / "out" / "images"
    recs = PDFVisualExtractor(pdf, images).extract(want_figures=False)
    assert any(r.kind == "opener" for r in recs)
    opener = next(r for r in recs if r.kind == "opener")
    assert (tmp_path / "out" / opener.rel_path).exists()


def test_document_builder_groups_sections():
    from idml2mobile.model.builder import DocumentBuilder

    heading = TextBlock(BlockType.HEADING, runs=[InlineRun(text="Intro")])
    para = TextBlock(BlockType.PARAGRAPH, runs=[InlineRun(text="hello world.")])
    doc = DocumentBuilder(title="T").add_blocks([heading, para]).build()
    assert isinstance(doc, Document)
    assert len(doc.sections) == 1
    sec = doc.sections[0]
    assert isinstance(sec, Section)
    assert sec.title == "Intro"
    assert len(sec.children) == 2
