from idml2mobile.parsers.base import Frame
from idml2mobile.reading_order.strategies import (
    AutoStrategy,
    GeometricColumnStrategy,
    ThreadedOrderStrategy,
)


def _frame(fid, story, page, col, y, kind="text", **kw):
    return Frame(self_id=fid, kind=kind, story_id=story, page_index=page,
                 column=col, y=y, x=col * 300, **kw)


def test_geometric_left_column_before_right():
    frames = [
        _frame("f_right", "s_right", page=0, col=1, y=10),
        _frame("f_left", "s_left", page=0, col=0, y=10),
    ]
    groups = GeometricColumnStrategy().order(frames)
    assert [g.story_id for g in groups] == ["s_left", "s_right"]


def test_geometric_top_to_bottom_within_column():
    frames = [
        _frame("f_b", "s_b", page=0, col=0, y=200),
        _frame("f_a", "s_a", page=0, col=0, y=20),
    ]
    groups = GeometricColumnStrategy().order(frames)
    assert [g.story_id for g in groups] == ["s_a", "s_b"]


def test_story_emitted_once_across_threaded_frames():
    frames = [
        _frame("f1", "s1", page=0, col=0, y=20, next_frame="f2"),
        _frame("f2", "s1", page=0, col=1, y=20, prev_frame="f1"),
    ]
    groups = ThreadedOrderStrategy().order(frames)
    story_groups = [g for g in groups if g.kind == "story"]
    assert len(story_groups) == 1
    assert story_groups[0].story_id == "s1"


def test_auto_picks_threaded_when_threading_present():
    frames = [_frame("f1", "s1", 0, 0, 10, next_frame="f2")]
    groups = AutoStrategy().order(frames)
    assert len(groups) == 1


def test_images_interleave_by_position():
    frames = [
        _frame("t", "s", page=0, col=0, y=100),
        _frame("img", "", page=0, col=0, y=10, kind="image", link_uri="x.png"),
    ]
    groups = GeometricColumnStrategy().order(frames)
    assert groups[0].kind == "image"  # image is higher on the page
    assert groups[1].kind == "story"
