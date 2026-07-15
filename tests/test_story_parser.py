from idml2mobile.idml.package import IDMLPackage
from idml2mobile.parsers.factory import ParserFactory


def test_story_parser_extracts_text_and_styles(sample_idml):
    with IDMLPackage(sample_idml) as pkg:
        stories = {}
        for path in pkg.stories():
            raw = ParserFactory.for_story(path).parse()
            stories[raw.story_id] = raw

    assert "ustory1" in stories
    s1 = stories["ustory1"]
    # heading + body paragraph
    assert len(s1.paragraphs) == 2
    assert s1.paragraphs[0].text == "Solutions"
    assert s1.paragraphs[0].para_style == "Heading 1"
    # bold run preserved in the body paragraph
    body = s1.paragraphs[1]
    assert body.text == "Water boils at a lower temperature at altitude."
    assert any(r.bold and r.text == "lower" for r in body.runs)


def test_story_parser_captures_inline_anchored_image(sample_idml):
    with IDMLPackage(sample_idml) as pkg:
        raw = None
        for path in pkg.stories():
            r = ParserFactory.for_story(path).parse()
            if r.story_id == "ustory2":
                raw = r
    assert raw is not None
    option = raw.paragraphs[1]
    image_runs = [r for r in option.runs if r.is_image]
    assert len(image_runs) == 1
    assert image_runs[0].image_uri.endswith("eqn.wmf")
    # text around the image is preserved
    assert "moles per litre" in option.text
