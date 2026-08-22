"""Snapping a route point onto an iso-height line.

Over a made-up height function, so what the snap does is arithmetic anybody can
check: a road along a hillside runs at a constant height, and this is what puts
the points there.
"""
import numpy as np
import pytest
import support
from support import pointer_at as _at

from glisteel_editor.editing import RouteEditor, RouteTool


def _ramp(x, z):
    """Ground rising one in ten towards the east."""
    return np.asarray(x, dtype='d') * 0.1


def _editor(points=(), **named):
    named.setdefault('height_fn', _ramp)
    return RouteEditor(support.route(points, closed=False), **named)


class TestPlacingWithSnapOn:
    def test_a_point_lands_on_a_contour(self) -> None:
        editor = _editor(snap=True, snap_interval=25.0)
        editor.append(np.array([137.0, 0.0, 40.0]))
        x, _z = editor.route.points[0]
        assert float(_ramp(np.asarray([x]), np.asarray([0.0]))[0]) \
            == pytest.approx(25.0, abs=0.05)

    def test_with_snap_off_it_lands_where_the_pointer_was(self) -> None:
        editor = _editor(snap=False)
        editor.append(np.array([137.0, 0.0, 40.0]))
        assert editor.route.points[0] == pytest.approx((137.0, 40.0))

    def test_dragging_a_point_snaps_it_too(self) -> None:
        editor = _editor(points=[(0.0, 0.0)], snap=True, snap_interval=25.0)
        editor.move(0, np.array([137.0, 0.0, 40.0]))
        x, _z = editor.route.points[0]
        assert float(_ramp(np.asarray([x]), np.asarray([0.0]))[0]) \
            == pytest.approx(25.0, abs=0.05)

    def test_a_point_put_into_the_line_snaps_as_well(self) -> None:
        """Onto the height of the point it comes after, like any other."""
        editor = _editor(points=[(300.0, 0.0), (700.0, 0.0)], snap=True,
                         snap_interval=25.0)
        editor.insert(1, np.array([137.0, 0.0, 40.0]))
        x, _z = editor.route.points[1]
        assert float(_ramp(np.asarray([x]), np.asarray([0.0]))[0]) \
            == pytest.approx(30.0, abs=0.05)

    def test_it_follows_the_contour_the_line_is_already_on(self) -> None:
        """The point of it: a road along a hillside holds one height, so the
        second point takes the first one's contour rather than the nearest."""
        editor = _editor(points=[(300.0, 0.0)], snap=True, snap_interval=25.0)
        editor.append(np.array([137.0, 0.0, 200.0]))
        x, _z = editor.route.points[1]
        assert float(_ramp(np.asarray([x]), np.asarray([0.0]))[0]) \
            == pytest.approx(30.0, abs=0.05)

    def test_the_first_point_has_no_contour_to_follow(self) -> None:
        editor = _editor(snap=True, snap_interval=25.0)
        editor.append(np.array([137.0, 0.0, 40.0]))
        assert editor.route.points[0][0] != pytest.approx(137.0)

    def test_it_does_not_drag_a_point_across_the_map(self) -> None:
        editor = _editor(snap=True, snap_interval=25.0, snap_reach=20.0)
        editor.append(np.array([137.0, 0.0, 0.0]))
        assert abs(editor.route.points[0][0] - 137.0) <= 20.0

    def test_an_editor_with_no_height_field_leaves_points_alone(self) -> None:
        editor = RouteEditor(support.route(closed=False), snap=True)
        editor.append(np.array([137.0, 0.0, 40.0]))
        assert editor.route.points[0] == pytest.approx((137.0, 40.0))


class TestTurningItOn:
    def test_a_fresh_editor_places_points_where_the_pointer_is(self) -> None:
        assert not _editor().snap

    def test_the_tool_toggles_it(self) -> None:
        editor = _editor(snap=False)
        tool = RouteTool(editor=editor)
        assert tool.on_key('h', (0, 0, 0))
        assert editor.snap
        assert tool.on_key('h', (0, 0, 0))
        assert not editor.snap

    def test_holding_shift_snaps_without_turning_it_on(self) -> None:
        """A designer who wants one point on a contour should not have to
        remember to turn the mode off again."""
        editor = _editor(snap=False, snap_interval=25.0)
        tool = RouteTool(editor=editor)
        pointer = _at(137.0, 40.0)
        pointer.modifiers = (1, 0, 0)
        tool.on_press(pointer)
        x, _z = editor.route.points[0]
        assert float(_ramp(np.asarray([x]), np.asarray([0.0]))[0]) \
            == pytest.approx(25.0, abs=0.05)
        assert not editor.snap

    def test_without_shift_and_with_snap_off_nothing_moves(self) -> None:
        editor = _editor(snap=False)
        RouteTool(editor=editor).on_press(_at(137.0, 40.0))
        assert editor.route.points[0] == pytest.approx((137.0, 40.0))

    def test_holding_shift_with_snap_on_turns_it_off_for_that_point(self) -> None:
        """The modifier means "the other way", whichever way the mode is."""
        editor = _editor(snap=True, snap_interval=25.0)
        tool = RouteTool(editor=editor)
        pointer = _at(137.0, 40.0)
        pointer.modifiers = (1, 0, 0)
        tool.on_press(pointer)
        assert editor.route.points[0] == pytest.approx((137.0, 40.0))
