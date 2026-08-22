"""Sculpting the land with the pointer, and taking it back again.

Driven by made-up events: a brush is a position, a radius and a direction, and
one gesture is one undoable change to the project's landscape.
"""
import numpy as np
import pytest
from support import pointer_at as _at, pointer_over_nothing

from glisteel_editor.project import new_project
from glisteel_editor.sculpting import LandEditor, SculptTool


def _editor(**named):
    project = new_project(extent=2048.0)
    changed = []
    return LandEditor(project.landscape, on_change=lambda: changed.append(1),
                      **named), project, changed


class TestOneStroke:
    def test_a_drag_puts_one_stroke_on_the_landscape(self) -> None:
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_press(_at(10.0, 20.0))
        tool.on_drag(_at(12.0, 22.0))
        tool.on_release(_at(12.0, 22.0))
        assert len(project.landscape.source.edits) == 1

    def test_the_stroke_is_where_the_pointer_was(self) -> None:
        editor, project, _changed = _editor()
        SculptTool(editor=editor).on_press(_at(-40.0, 90.0))
        assert project.landscape.source.edits[0].centre == (-40.0, 90.0)

    def test_it_raises_the_ground_by_default(self) -> None:
        editor, project, _changed = _editor()
        SculptTool(editor=editor).on_press(_at(0.0, 0.0))
        assert project.landscape.source.edits[0].amount > 0

    def test_the_right_button_lowers_it(self) -> None:
        editor, project, _changed = _editor()
        SculptTool(editor=editor).on_press(_at(0.0, 0.0, button=2))
        assert project.landscape.source.edits[0].amount < 0

    def test_a_gesture_that_wanders_moves_the_stroke_with_it(self) -> None:
        """Rather than leaving a hundred strokes behind the pointer."""
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(30.0, 0.0))
        tool.on_drag(_at(60.0, 0.0))
        assert len(project.landscape.source.edits) == 1
        assert project.landscape.source.edits[0].centre[0] == 60.0

    def test_the_land_says_it_changed(self) -> None:
        editor, _project, changed = _editor()
        SculptTool(editor=editor).on_press(_at(0.0, 0.0))
        assert changed


class TestTheBrush:
    def test_the_wheel_makes_it_wider_and_narrower(self) -> None:
        editor, _project, _changed = _editor()
        wide = editor.radius
        editor.grow(1)
        assert editor.radius > wide
        editor.grow(-1)
        assert editor.radius == pytest.approx(wide)

    def test_it_never_shrinks_to_nothing(self) -> None:
        editor, _project, _changed = _editor()
        for _ in range(80):
            editor.grow(-1)
        assert editor.radius >= LandEditor.SMALLEST

    def test_keys_change_how_hard_it_pushes(self) -> None:
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        before = editor.strength
        assert tool.on_key(']', (0, 0, 0))
        assert editor.strength > before
        assert tool.on_key('[', (0, 0, 0))
        assert editor.strength == pytest.approx(before)

    def test_the_stroke_it_lays_down_is_the_brush_it_has(self) -> None:
        editor, project, _changed = _editor()
        editor.radius = 250.0
        editor.strength = 40.0
        SculptTool(editor=editor).on_press(_at(0.0, 0.0))
        stroke = project.landscape.source.edits[0]
        assert stroke.radius == 250.0
        assert stroke.amount == pytest.approx(40.0)


class TestTakingItBack:
    def test_undo_removes_the_whole_gesture(self) -> None:
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        for step in range(10):
            tool.on_drag(_at(float(step) * 5.0, 0.0))
        tool.on_release(_at(45.0, 0.0))
        assert editor.undo()
        assert project.landscape.source.edits == []

    def test_redo_puts_it_back(self) -> None:
        editor, project, _changed = _editor()
        SculptTool(editor=editor).on_press(_at(5.0, 5.0))
        editor.undo()
        assert editor.redo()
        assert len(project.landscape.source.edits) == 1

    def test_undo_with_nothing_done_says_so(self) -> None:
        editor, _project, _changed = _editor()
        assert not editor.undo()

    def test_escape_abandons_a_stroke_half_way_through(self) -> None:
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(50.0, 0.0))
        tool.cancel()
        assert project.landscape.source.edits == []

    def test_strokes_undo_one_at_a_time(self) -> None:
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        for where in ((0.0, 0.0), (200.0, 0.0), (400.0, 0.0)):
            tool.on_press(_at(*where))
            tool.on_release(_at(*where))
        editor.undo()
        assert len(project.landscape.source.edits) == 2


class TestWhatItLeavesAlone:
    def test_it_does_not_take_a_click_over_nothing(self) -> None:
        editor, project, _changed = _editor()
        tool = SculptTool(editor=editor)
        assert not tool.on_press(pointer_over_nothing())
        assert project.landscape.source.edits == []

    def test_it_is_called_something_a_designer_recognises(self) -> None:
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        assert tool.name == 'sculpt'
        assert tool.label


class TestWhatTheGroundDoes:
    def test_a_raised_stroke_lifts_the_ground_under_it(self) -> None:
        editor, project, _changed = _editor()
        before = float(project.landscape.source.height_fn()(
            np.asarray([0.0]), np.asarray([0.0]))[0])
        SculptTool(editor=editor).on_press(_at(0.0, 0.0))
        after = float(project.landscape.source.height_fn()(
            np.asarray([0.0]), np.asarray([0.0]))[0])
        assert after > before + 1.0


class TestKnowingWhereTheBrushIs:
    def test_a_move_puts_the_brush_under_the_pointer(self) -> None:
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        assert tool.on_move(_at(30.0, -40.0))
        assert editor.at == (30.0, -40.0)

    def test_it_starts_nowhere(self) -> None:
        editor, _project, _changed = _editor()
        assert editor.at is None

    def test_leaving_the_tool_puts_the_brush_away(self) -> None:
        """Or its ring is left on the map under a tool that is not sculpting."""
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_move(_at(30.0, -40.0))
        tool.leave()
        assert editor.at is None

    def test_a_move_over_nothing_leaves_it_where_it_was(self) -> None:
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_move(_at(30.0, -40.0))
        assert not tool.on_move(pointer_over_nothing())
        assert editor.at == (30.0, -40.0)

    def test_a_drag_takes_the_brush_with_it(self) -> None:
        editor, _project, _changed = _editor()
        tool = SculptTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(70.0, 10.0))
        assert editor.at == (70.0, 10.0)
