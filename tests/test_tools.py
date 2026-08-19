"""The tools a designer can put the pointer into, and what each of them does.

Driven by made-up events: a tool is a thing that answers a pointer, and none of
that is a window.
"""
import pytest
from OpenGLContext.edit.maptools import PanTool
from OpenGLContext.edit.mapview import MapView
from OpenGLContext.ui.metrics import REFERENCE_METRICS
from OpenGLContext.ui.toolpalette import ToolButton, ToolPalette

from glisteel_editor.controls import MapControls
from glisteel_editor.editing import RouteEditor, RouteTool, editor_tools
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


def _editor(points=()):
    route = Route(name='circuit', closed=True, points=[tuple(p) for p in points])
    return RouteEditor(route)


def _rig(points=(), span=600.0):
    editor = _editor(points)
    view = MapView(centre=(0.0, 0.0), span=span)
    moved = []
    tools = editor_tools(editor, view, lambda: VIEWPORT,
                         on_change=lambda: moved.append(1))
    controls = MapControls(view, tools, lambda: VIEWPORT, editor=editor)
    return tools, controls, editor, view, moved


class TestWhatTheEditorOffers:
    def test_it_offers_drawing_the_line_and_moving_the_map(self) -> None:
        tools, _c, _e, _v, _m = _rig()
        assert [tool.name for tool in tools.tools] == ['route', 'start', 'pan']

    def test_drawing_is_what_the_pointer_starts_in(self) -> None:
        tools, _c, _e, _v, _m = _rig()
        assert tools.active is not None and tools.active.name == 'route'

    def test_every_tool_says_what_it_is_called(self) -> None:
        tools, _c, _e, _v, _m = _rig()
        assert all(tool.label for tool in tools.tools)

    def test_the_route_tool_is_wired_to_the_route_being_drawn(self) -> None:
        tools, _c, editor, _v, _m = _rig()
        route_tool = tools.named('route')
        assert isinstance(route_tool, RouteTool)
        assert route_tool.editor is editor

    def test_the_pan_tool_is_wired_to_the_map(self) -> None:
        tools, _c, _e, view, _m = _rig()
        pan = tools.named('pan')
        assert isinstance(pan, PanTool)
        assert pan.view is view


class TestPuttingThePointerIntoATool:
    def test_a_click_draws_while_the_route_tool_is_in_force(self) -> None:
        _t, controls, editor, _v, _m = _rig()
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        assert len(editor.route.points) == 1

    def test_a_click_does_not_draw_while_the_pan_tool_is_in_force(self) -> None:
        tools, controls, editor, _v, _m = _rig()
        tools.select('pan')
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        assert editor.route.points == []

    def test_a_left_drag_moves_the_map_in_the_pan_tool(self) -> None:
        tools, controls, _e, view, _m = _rig()
        tools.select('pan')
        controls.button(_Event(400, 300, 0, 1))
        controls.moved(_Event(440, 300))
        assert view.centre[0] == pytest.approx(-40.0)

    def test_the_map_still_moves_on_the_right_button_while_drawing(self) -> None:
        """What a tool does not want is still the map's."""
        _t, controls, _e, view, _m = _rig()
        controls.button(_Event(400, 300, 2, 1))
        controls.moved(_Event(440, 300))
        assert view.centre[0] == pytest.approx(-40.0)


class TestThePalette:
    def _palette(self, tools):
        palette = ToolPalette(tools=tools, reserved=30.0)
        palette.layout((1280, 800), REFERENCE_METRICS)
        return palette

    def _buttons(self, palette):
        return [w for w in palette.walk() if isinstance(w, ToolButton)]

    def test_it_shows_the_tools_the_editor_has(self) -> None:
        tools, _c, _e, _v, _m = _rig()
        palette = self._palette(tools)
        assert [b.text for b in self._buttons(palette)] \
            == [tool.label for tool in tools.tools]

    def test_clicking_moving_the_map_stops_the_next_click_drawing(self) -> None:
        """The whole point of the strip: say what the pointer is for."""
        tools, controls, editor, _v, _m = _rig()
        palette = self._palette(tools)
        pan_button = self._buttons(palette)[1]
        x, y = pan_button.rect.centre
        palette.pointer_pressed(x, y, 0)
        palette.pointer_released(x, y, 0)
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        assert editor.route.points == []

    def test_the_strip_says_which_tool_is_in_force(self) -> None:
        tools, _c, _e, _v, _m = _rig()
        palette = self._palette(tools)
        tools.select('pan')
        lit = [button.text for button in self._buttons(palette)
               if button.active()]
        assert lit == [tools.named('pan').label]


class TestSculptingAmongTheTools:
    def _rig_with_land(self, points=()):
        from glisteel_editor.project import new_project
        from glisteel_editor.sculpting import LandEditor
        project = new_project(extent=2048.0, points=points)
        editor = RouteEditor(project.route())
        view = MapView(centre=(0.0, 0.0), span=600.0)
        land = LandEditor(project.landscape)
        tools = editor_tools(editor, view, lambda: VIEWPORT, land=land)
        controls = MapControls(view, tools, lambda: VIEWPORT, editor=editor)
        return tools, controls, project, land

    def test_the_editor_offers_it(self) -> None:
        tools, _c, _p, _land = self._rig_with_land()
        assert 'sculpt' in [tool.name for tool in tools.tools]

    def test_drawing_is_still_what_the_pointer_starts_in(self) -> None:
        tools, _c, _p, _land = self._rig_with_land()
        assert tools.active.name == 'route'

    def test_a_drag_raises_ground_once_it_is_chosen(self) -> None:
        tools, controls, project, _land = self._rig_with_land()
        tools.select('sculpt')
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        assert len(project.landscape.source.edits) == 1

    def test_the_wheel_sizes_the_brush_instead_of_the_map(self) -> None:
        tools, controls, _p, land = self._rig_with_land()
        tools.select('sculpt')
        span = controls.view.span
        was = land.radius
        controls.button(_Event(400, 300, 4, 1))
        assert land.radius != was
        assert controls.view.span == span

    def test_the_wheel_still_zooms_while_drawing(self) -> None:
        tools, controls, _p, _land = self._rig_with_land()
        span = controls.view.span
        controls.button(_Event(400, 300, 4, 1))
        assert controls.view.span != span

    def test_undo_takes_back_what_the_tool_in_force_did(self) -> None:
        tools, controls, project, _land = self._rig_with_land()
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        tools.select('sculpt')
        controls.button(_Event(420, 320, 0, 1))
        controls.button(_Event(420, 320, 0, 0))
        assert tools.undo()
        assert project.landscape.source.edits == []
        assert len(project.route().points) == 1

    def test_undo_in_the_route_tool_takes_back_the_route(self) -> None:
        tools, controls, project, _land = self._rig_with_land()
        controls.button(_Event(400, 300, 0, 1))
        controls.button(_Event(400, 300, 0, 0))
        assert tools.undo()
        assert project.route().points == []
