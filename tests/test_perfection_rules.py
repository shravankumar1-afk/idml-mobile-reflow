from pathlib import Path

from idml2mobile.config import ConversionConfig
from idml2mobile.mathconv.mathml import extract_mathtype_latex
from idml2mobile.model.blocks import BlockType, InlineRun, TextBlock
from idml2mobile.parsers.story_parser import StoryParser
from idml2mobile.pipeline import ConversionPipeline


def _text(value: str, kind: BlockType = BlockType.PARAGRAPH) -> TextBlock:
    return TextBlock(kind, [InlineRun(text=value)])


def test_mathtype_wmf_embedded_mathml_becomes_latex(tmp_path: Path) -> None:
    wmf = tmp_path / "eq.wmf"
    wmf.write_bytes(
        b"prefix<math xmlns='http://www.w3.org/1998/Math/MathML'>"
        b"<mfrac><mi>x</mi><mn>2</mn></mfrac></math>suffix"
    )
    assert extract_mathtype_latex(wmf) == r"\frac{x}{2}"


def test_legacy_mt_extra_symbols_are_portable_unicode() -> None:
    assert StoryParser._symbol_text("\uf06c \uf083 \uf051", "MT Extra") == "l ⇌ C"


def test_example_ribbon_is_hoisted_before_question(tmp_path: Path) -> None:
    pipeline = ConversionPipeline(ConversionConfig(tmp_path, tmp_path / "out"))
    q = _text("Calculate this value.", BlockType.QUESTION)
    ex = _text("Ex-5")
    sol = _text("Sol. Working", BlockType.SOLUTION)
    grouped = pipeline._group_examples([q, ex, sol])
    assert grouped == [ex, q, sol]


def test_check_understanding_header_moves_above_question_run(tmp_path: Path) -> None:
    pipeline = ConversionPipeline(ConversionConfig(tmp_path, tmp_path / "out"))
    q1 = _text("1. First?", BlockType.QUESTION)
    q2 = _text("2. Second?", BlockType.QUESTION)
    head = _text("Check Your Understanding", BlockType.SUBHEADING)
    q3 = _text("3. Third?", BlockType.QUESTION)
    blocks = pipeline._hoist_question_headers([q1, q2, head, q3])
    assert blocks[0] is head
    assert head.box_group == q1.box_group == q2.box_group == q3.box_group

