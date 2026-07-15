from idml2mobile.cleanup.passes import CleanupChain
from idml2mobile.model.blocks import BlockType, InlineRun, TextBlock


def test_cleanup_keeps_equation_only_image_runs():
    block = TextBlock(BlockType.PARAGRAPH, [InlineRun(is_image=True, original_ref="eq.wmf")])
    cleaned = CleanupChain().run([block])
    assert cleaned == [block]
    assert cleaned[0].runs[0].original_ref == "eq.wmf"
