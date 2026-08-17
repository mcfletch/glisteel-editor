"""Drawing a route: what the pointer does, and what the line does about it.

The editing itself is arithmetic on a list of points and a hit test in metres,
so all of it runs without a window. What is asserted here is the behaviour a
designer would describe: click on empty ground and a point appears at the end;
click on a point and drag it and it moves; click on the line between two points
and a new one appears *there*, in order, rather than at the end.
"""
import numpy as np
import pytest
from OpenGLContext.edit.tools import Pointer, ToolManager

from glisteel_editor.editing import RouteEditor, RouteTool
from glisteel_editor.project import Route


def _route(points=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0))):
    return Route(name='circuit', closed=True, points=[tuple(p) for p in points])


def _editor(route=None, reach=10.0):
    return RouteEditor(route or _route(), reach=reach)


def _at(x, z, button=0, modifiers=(0, 0, 0)):
    """A pointer over a world point, as the map view reports one."""
    return Pointer(x=0.0, y=0.0, world=np.array([x, 0.0, z]),
                   button=button, modifiers=modifiers)


class TestFindingWhatIsUnderThePointer:
    def test_it_finds_a_point_it_is_over(self) -> None:
        assert _editor().point_at((100.0, 2.0)) == 1

    def test_it_finds_nothing_where_there_is_nothing(self) -> None:
        assert _editor().point_at((50.0, 50.0)) is None

    def test_the_reach_is_in_metres_and_can_be_set(self) -> None:
        assert _editor(reach=1.0).point_at((100.0, 2.0)) is None
        assert _editor(reach=40.0).point_at((100.0, 20.0)) == 1

    def test_the_nearest_point_wins(self) -> None:
        editor = _editor(reach=200.0)
        assert editor.point_at((90.0, 5.0)) == 1

    def test_it_finds_the_segment_the_pointer_is_on(self) -> None:
        """Between point 0 and point 1, so a new point there is number 1."""
        assert _editor().segment_at((50.0, 1.0)) == 1

    def test_a_closed_route_has_a_segment_home_again(self) -> None:
        assert _editor().segment_at((0.0, 50.0)) == 4

    def test_an_open_route_does_not(self) -> None:
        route = _route()
        route.closed = False
        assert RouteEditor(route, reach=10.0).segment_at((0.0, 50.0)) is None

    def test_it_finds_no_segment_out_in_the_field(self) -> None:
        assert _editor().segment_at((500.0, 500.0)) is None


class TestChangingTheLine:
    def test_a_point_can_be_added_at_the_end(self) -> None:
        editor = _editor(_route(points=[(0.0, 0.0)]))
        editor.append((50.0, 60.0))
        assert editor.route.points[-1] == (50.0, 60.0)

    def test_a_point_can_be_put_into_the_middle(self) -> None:
        editor = _editor()
        editor.insert(1, (50.0, 0.0))
        assert editor.route.points[1] == (50.0, 0.0)
        assert len(editor.route.points) == 5

    def test_a_point_can_be_moved(self) -> None:
        editor = _editor()
        editor.move(2, (140.0, 90.0))
        assert editor.route.points[2] == (140.0, 90.0)

    def test_a_point_can_be_taken_out(self) -> None:
        editor = _editor()
        editor.remove(1)
        assert len(editor.route.points) == 3
        assert (100.0, 0.0) not in editor.route.points

    def test_taking_out_what_is_not_there_changes_nothing(self) -> None:
        editor = _editor()
        editor.remove(99)
        assert len(editor.route.points) == 4

    def test_every_change_is_announced(self) -> None:
        seen = []
        editor = _editor()
        editor.on_change = lambda: seen.append(1)
        editor.append((1.0, 1.0))
        editor.move(0, (2.0, 2.0))
        editor.remove(0)
        editor.insert(0, (3.0, 3.0))
        assert len(seen) == 4

    def test_a_change_that_does_nothing_is_not_announced(self) -> None:
        seen = []
        editor = _editor()
        editor.on_change = lambda: seen.append(1)
        editor.remove(99)
        assert seen == []


class TestDrawingWithThePointer:
    def _tool(self, route=None):
        editor = _editor(route)
        tool = RouteTool(name='route', editor=editor)
        return ToolManager([tool]), editor

    def test_clicking_empty_ground_puts_a_point_at_the_end(self) -> None:
        tools, editor = self._tool(_route(points=[(0.0, 0.0)]))
        tools.press(_at(300.0, 300.0))
        tools.release(_at(300.0, 300.0))
        assert editor.route.points[-1] == (300.0, 300.0)

    def test_clicking_on_the_line_puts_one_there(self) -> None:
        tools, editor = self._tool()
        tools.press(_at(50.0, 1.0))
        tools.release(_at(50.0, 1.0))
        assert editor.route.points[1] == (50.0, 1.0)

    def test_dragging_a_point_moves_it(self) -> None:
        tools, editor = self._tool()
        tools.press(_at(100.0, 2.0))
        tools.move(_at(160.0, 40.0))
        tools.release(_at(160.0, 40.0))
        assert editor.route.points[1] == (160.0, 40.0)

    def test_a_drag_that_is_abandoned_puts_the_point_back(self) -> None:
        tools, editor = self._tool()
        before = list(editor.route.points)
        tools.press(_at(100.0, 2.0))
        tools.move(_at(160.0, 40.0))
        tools.key('<escape>', (0, 0, 0))
        assert editor.route.points == before

    def test_dragging_a_point_does_not_also_add_one(self) -> None:
        tools, editor = self._tool()
        tools.press(_at(100.0, 2.0))
        tools.move(_at(160.0, 40.0))
        tools.release(_at(160.0, 40.0))
        assert len(editor.route.points) == 4

    def test_the_right_button_takes_a_point_out(self) -> None:
        tools, editor = self._tool()
        tools.press(_at(100.0, 2.0, button=2))
        tools.release(_at(100.0, 2.0, button=2))
        assert len(editor.route.points) == 3

    def test_the_right_button_over_nothing_is_left_for_the_camera(self) -> None:
        """So a right-drag still orbits, which is what it is for."""
        tools, _editor = self._tool()
        assert tools.press(_at(500.0, 500.0, button=2)) is False

    def test_a_click_over_the_sky_is_not_a_point(self) -> None:
        tools, editor = self._tool()
        nowhere = Pointer(x=0.0, y=0.0, world=None)
        assert tools.press(nowhere) is False
        assert len(editor.route.points) == 4

    def test_delete_takes_out_what_is_selected(self) -> None:
        tools, editor = self._tool()
        tools.move(_at(100.0, 2.0))
        tools.key('<delete>', (0, 0, 0))
        assert len(editor.route.points) == 3

    def test_delete_with_nothing_under_the_pointer_does_nothing(self) -> None:
        tools, editor = self._tool()
        tools.move(_at(500.0, 500.0))
        assert tools.key('<delete>', (0, 0, 0)) is False
        assert len(editor.route.points) == 4

    def test_the_point_under_the_pointer_is_reported_for_drawing(self) -> None:
        tools, editor = self._tool()
        tools.move(_at(100.0, 2.0))
        assert editor.hovered == 1
        tools.move(_at(500.0, 500.0))
        assert editor.hovered is None


class TestClosingTheCircuit:
    def test_a_route_can_be_told_to_close(self) -> None:
        editor = _editor()
        editor.route.closed = False
        editor.close_route(True)
        assert editor.route.closed

    def test_closing_it_is_a_change(self) -> None:
        seen = []
        editor = _editor()
        editor.on_change = lambda: seen.append(1)
        editor.close_route(False)
        assert seen == [1]

    def test_saying_what_it_already_is_is_not(self) -> None:
        seen = []
        editor = _editor()
        editor.on_change = lambda: seen.append(1)
        editor.close_route(True)
        assert seen == []


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestTakingItBack:
    """An editor that cannot undo loses work, and a designer drawing a line
    with the pointer makes a wrong point every few minutes."""

    def _editor(self):
        return RouteEditor(_route(), reach=10.0)

    def test_a_point_added_can_be_taken_back(self) -> None:
        editor = self._editor()
        editor.append((500.0, 500.0))
        assert editor.undo() is True
        assert (500.0, 500.0) not in editor.route.points

    def test_a_point_moved_goes_back_where_it_was(self) -> None:
        editor = self._editor()
        before = list(editor.route.points)
        editor.move(1, (900.0, 900.0))
        editor.undo()
        assert editor.route.points == before

    def test_a_point_taken_out_comes_back(self) -> None:
        editor = self._editor()
        before = list(editor.route.points)
        editor.remove(2)
        editor.undo()
        assert editor.route.points == before

    def test_it_comes_back_where_it_was_in_the_line(self) -> None:
        """Not on the end: a route is an order."""
        editor = self._editor()
        before = list(editor.route.points)
        editor.remove(1)
        editor.undo()
        assert editor.route.points[1] == before[1]

    def test_closing_the_route_can_be_taken_back(self) -> None:
        editor = self._editor()
        editor.close_route(False)
        editor.undo()
        assert editor.route.closed

    def test_several_steps_come_back_in_turn(self) -> None:
        editor = self._editor()
        editor.append((10.0, 10.0))
        editor.append((20.0, 20.0))
        editor.undo()
        assert editor.route.points[-1] == (10.0, 10.0)
        editor.undo()
        assert (10.0, 10.0) not in editor.route.points

    def test_with_nothing_to_undo_it_says_so(self) -> None:
        assert self._editor().undo() is False

    def test_undoing_is_a_change_like_any_other(self) -> None:
        seen = []
        editor = self._editor()
        editor.append((1.0, 1.0))
        editor.on_change = lambda: seen.append(1)
        editor.undo()
        assert seen == [1]

    def test_what_was_undone_can_be_done_again(self) -> None:
        editor = self._editor()
        editor.append((500.0, 500.0))
        editor.undo()
        assert editor.redo() is True
        assert editor.route.points[-1] == (500.0, 500.0)

    def test_with_nothing_to_redo_it_says_so(self) -> None:
        assert self._editor().redo() is False

    def test_a_fresh_change_forgets_what_was_undone(self) -> None:
        """Or redo would put back a line that never existed."""
        editor = self._editor()
        editor.append((500.0, 500.0))
        editor.undo()
        editor.append((1.0, 2.0))
        assert editor.redo() is False

    def test_it_does_not_remember_for_ever(self) -> None:
        editor = self._editor()
        for i in range(RouteEditor.HISTORY * 3):
            editor.append((float(i), 0.0))
        undone = 0
        while editor.undo():
            undone += 1
        assert undone == RouteEditor.HISTORY

    def test_a_drag_is_one_step_rather_than_one_per_pixel(self) -> None:
        """A point dragged across the map moves a hundred times; taking that
        back a hundred times is not undo."""
        editor = self._editor()
        before = list(editor.route.points)
        editor.begin_step()
        for x in range(200, 260):
            editor.move(1, (float(x), 0.0))
        editor.end_step()
        assert editor.undo() is True
        assert editor.route.points == before
