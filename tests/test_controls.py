"""What the pointer did, and what the map and the tools do about it.

Driven by made-up events, because none of this is a window: a click is a
position, a button and a state, and what it means is arithmetic against the
map's scale.
"""
import pytest
from OpenGLContext.edit.mapview import MapView
from OpenGLContext.edit.tools import ToolManager

from glisteel_editor.controls import MapControls
from glisteel_editor.editing import RouteEditor, RouteTool
from glisteel_editor.project import Route

VIEWPORT = (800, 600)


class _Event:
    """As much of a mouse event as the controls read."""

    def __init__(self, x, y, button=0, state=1, modifiers=(0, 0, 0)):
        self.pickPoint = (x, y)
        self.button = button
        self.state = state
        self._modifiers = modifiers

    def getPickPoint(self):
        return self.pickPoint

    def getModifiers(self):
        return self._modifiers


def _controls(points=(), span=600.0, centre=(0.0, 0.0)):
    route = Route(name='circuit', closed=True, points=[tuple(p) for p in points])
    editor = RouteEditor(route)
    tools = ToolManager([RouteTool(editor=editor)])
    view = MapView(centre=centre, span=span)
    settled = []
    controls = MapControls(view, tools, lambda: VIEWPORT, editor=editor,
                           on_settle=lambda: settled.append(1))
    return controls, editor, view, settled


class TestWhereThePointerIs:
    def test_the_middle_of_the_window_is_the_middle_of_the_map(self) -> None:
        controls, _editor, _view, _settled = _controls(centre=(120.0, -40.0))
        pointer = controls.pointer(_Event(400, 300))
        assert (float(pointer.world[0]), float(pointer.world[2])) \
            == pytest.approx((120.0, -40.0))

    def test_it_reads_the_ground_under_that_point(self) -> None:
        route = Route(name='circuit', points=[])
        editor = RouteEditor(route)
        tools = ToolManager([RouteTool(editor=editor)])
        controls = MapControls(MapView(span=600.0), tools, lambda: VIEWPORT,
                               height_at=lambda x, z: 42.0)
        assert float(controls.pointer(_Event(400, 300)).world[1]) == 42.0

    def test_it_carries_the_button(self) -> None:
        controls, _editor, _view, _settled = _controls()
        assert controls.pointer(_Event(10, 10, button=2)).button == 2


class TestDrawingThroughTheControls:
    def test_a_click_puts_a_point_where_the_pointer_is(self) -> None:
        controls, editor, _view, _settled = _controls()
        controls.button(_Event(400, 300, state=1))
        controls.button(_Event(400, 300, state=0))
        assert editor.route.points == [(0.0, 0.0)]

    def test_a_click_elsewhere_puts_it_there(self) -> None:
        controls, editor, _view, _settled = _controls(span=600.0)
        controls.button(_Event(500, 300, state=1))
        controls.button(_Event(500, 300, state=0))
        # 100 pixels right of the middle, at one metre a pixel.
        assert editor.route.points[0][0] == pytest.approx(100.0)

    def test_the_gesture_is_reported_finished(self) -> None:
        """So the road can be rebuilt when the line settles rather than while
        it is being dragged."""
        controls, _editor, _view, settled = _controls()
        controls.button(_Event(400, 300, state=1))
        controls.button(_Event(400, 300, state=0))
        assert settled == [1]

    def test_a_handle_is_the_same_size_to_grab_at_any_zoom(self) -> None:
        controls, editor, view, _settled = _controls(points=[(0.0, 0.0)])
        controls.button(_Event(400, 300, state=1))
        close = editor.reach
        view.zoom(4.0)
        controls.button(_Event(400, 300, state=0))
        controls.button(_Event(400, 300, state=1))
        assert editor.reach == pytest.approx(close * 4.0)

    def test_dragging_a_point_moves_it_across_the_map(self) -> None:
        controls, editor, _view, _settled = _controls(points=[(0.0, 0.0)])
        controls.button(_Event(400, 300, state=1))
        controls.moved(_Event(500, 300))
        controls.button(_Event(500, 300, state=0))
        assert editor.route.points[0][0] == pytest.approx(100.0)


class TestMovingTheMap:
    def test_a_drag_the_tools_do_not_want_pans(self) -> None:
        """The right button over open ground: the route tool has no use for
        it, so it moves the map."""
        controls, _editor, view, _settled = _controls(points=[(0.0, 0.0),
                                                              (50.0, 0.0)])
        controls.button(_Event(700, 500, button=2, state=1))
        controls.moved(_Event(750, 500))
        assert view.centre[0] == pytest.approx(-50.0)

    def test_it_stops_when_the_button_comes_up(self) -> None:
        controls, _editor, view, _settled = _controls(points=[(0.0, 0.0),
                                                              (50.0, 0.0)])
        controls.button(_Event(700, 500, button=2, state=1))
        controls.button(_Event(750, 500, button=2, state=0))
        controls.moved(_Event(300, 500))
        assert view.centre[0] == pytest.approx(0.0)

    def test_panning_adds_no_point(self) -> None:
        controls, editor, _view, _settled = _controls(points=[(0.0, 0.0),
                                                              (50.0, 0.0)])
        controls.button(_Event(700, 500, button=2, state=1))
        assert len(editor.route.points) == 2

    def test_the_wheel_zooms_in(self) -> None:
        controls, _editor, view, _settled = _controls(span=600.0)
        controls.button(_Event(400, 300, button=4, state=1))
        assert view.span < 600.0

    def test_the_other_way_zooms_out(self) -> None:
        controls, _editor, view, _settled = _controls(span=600.0)
        controls.button(_Event(400, 300, button=3, state=1))
        assert view.span > 600.0

    def test_zooming_holds_the_point_under_the_pointer(self) -> None:
        controls, _editor, view, _settled = _controls(span=600.0)
        before = view.world_from_screen(700, 500, VIEWPORT)
        controls.button(_Event(700, 500, button=4, state=1))
        assert view.world_from_screen(700, 500, VIEWPORT) \
            == pytest.approx(before, abs=1e-6)

    def test_the_wheel_coming_up_does_nothing_twice(self) -> None:
        controls, _editor, view, _settled = _controls(span=600.0)
        controls.button(_Event(400, 300, button=4, state=1))
        once = view.span
        controls.button(_Event(400, 300, button=4, state=0))
        assert view.span == once

    def test_framing_a_region_puts_it_on_screen(self) -> None:
        controls, _editor, view, _settled = _controls()
        controls.frame((-500.0, -400.0), (500.0, 400.0))
        assert view.centre == pytest.approx((0.0, 0.0))
        assert view.span >= 800.0

    def test_moving_the_map_is_announced(self) -> None:
        seen = []
        route = Route(name='circuit', points=[])
        editor = RouteEditor(route)
        controls = MapControls(MapView(span=600.0),
                               ToolManager([RouteTool(editor=editor)]),
                               lambda: VIEWPORT, editor=editor,
                               on_change=lambda: seen.append(1))
        controls.zoom(0.5)
        assert seen == [1]


class TestTheKeyboard:
    def test_a_key_a_tool_wants_is_taken(self) -> None:
        controls, editor, _view, _settled = _controls(points=[(0.0, 0.0)])
        controls.moved(_Event(400, 300, state=0))
        assert controls.key('<delete>', (0, 0, 0)) is True
        assert editor.route.points == []

    def test_a_key_it_does_not_is_left_alone(self) -> None:
        controls, _editor, _view, _settled = _controls()
        assert controls.key('w', (0, 0, 0)) is False


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
