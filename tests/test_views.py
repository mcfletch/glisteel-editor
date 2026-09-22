"""The views the editor draws the landscape through, and the layouts of them.

A designer works on the map, looks at the land from an angle, and -- when
placing something against the hillside rather than on the plan -- wants the
elevations beside both. The same cameras serve every arrangement, so a switch
shows what was already being looked at rather than jumping somewhere else.

Headless: views, cameras and arithmetic, with no window and no GL.
"""
from __future__ import annotations

import numpy as np
import pytest
from OpenGLContext.edit.mapview import MapView, MapViewPlatform
from OpenGLContext.edit.orbitview import OrbitView, OrbitViewPlatform
from OpenGLContext.edit.orthoview import OrthoViewPlatform
from OpenGLContext.events.mouseevents import WHEEL_UP

from glisteel_editor.views import LAYOUTS, EditorViews

WINDOW = (800, 600)
EXTENT = 2048.0
LOW, HIGH = (-EXTENT / 2.0, -EXTENT / 2.0), (EXTENT / 2.0, EXTENT / 2.0)
RELIEF = (0.0, 320.0)


def _views(**named) -> EditorViews:
    views = EditorViews(MapView(centre=(0.0, 0.0), span=EXTENT),
                        OrbitView(centre=(0.0, 0.0)), **named)
    views.arrange(*WINDOW)
    views.frame(LOW, HIGH, RELIEF)
    return views


def _centre_of(view):
    x, y, width, height = view.rect
    return x + width / 2.0, y + height / 2.0


def _ndc(view, point):
    clip = np.append(np.asarray(point, 'd'), 1.0) @ view.camera.matrix()
    return clip[:3] / clip[3]


class _Event:
    """A pointer event as the context delivers one."""

    view = None

    def __init__(self, x, y, button=0, state=1, kind='mousebutton'):
        self.type = kind
        self.button, self.state = button, state
        self._point = (x, y)

    def getPickPoint(self):
        return self._point

    def getModifiers(self):
        return (0, 0, 0)


class TestWhatItHolds:
    def test_the_map_the_elevations_and_the_angled_view(self):
        views = _views()
        assert isinstance(views.map.camera, MapViewPlatform)
        assert isinstance(views.angled.camera, OrbitViewPlatform)
        assert [view.name for view in views.elevations] == ['front', 'left']
        for view in views.elevations:
            assert isinstance(view.camera, OrthoViewPlatform)

    def test_the_elevations_can_be_chosen(self):
        views = _views(directions=('back', 'right'))
        assert [view.name for view in views.elevations] == ['back', 'right']

    def test_the_elevations_clear_to_a_flat_colour_and_the_others_to_the_sky(self):
        views = _views()
        for view in views.elevations:
            assert view.style.background not in (True, None)
        assert views.map.style.background is True
        assert views.angled.style.background is True

    def test_the_cameras_given_to_it_are_the_ones_it_draws_through(self):
        """The map camera is the editor's own, so the tools keep working on it."""
        plan, orbit = MapView(span=EXTENT), OrbitView()
        views = EditorViews(plan, orbit)
        assert views.map.camera.view is plan
        assert views.angled.camera.view is orbit


class TestTheLayouts:
    def test_the_map_alone_to_start_with(self):
        views = _views()
        assert views.mode == 'map'
        assert views.layout.views == [views.map]

    @pytest.mark.parametrize('name', LAYOUTS)
    def test_each_layout_is_shown_by_name(self, name):
        views = _views()
        assert views.show(name) is views.layout
        assert views.mode == name

    def test_the_split_puts_the_map_beside_the_angled_view(self):
        views = _views()
        views.show('split')
        assert views.layout.views == [views.map, views.angled]
        assert views.layout.arrangement == 'split'

    def test_the_quad_is_the_map_two_elevations_and_the_angled_view(self):
        views = _views()
        views.show('quad')
        assert views.layout.views == [views.map, views.elevations[0],
                                      views.elevations[1], views.angled]
        assert views.layout.arrangement == 'quad'

    def test_a_layout_nobody_has_is_a_usage_error(self):
        views = _views()
        with pytest.raises(ValueError) as raised:
            views.show('hexagonal')
        assert 'hexagonal' in str(raised.value)

    def test_a_view_on_screen_is_one_the_layout_shows(self):
        views = _views()
        assert views.showing(views.map) and not views.showing(views.angled)
        views.show('quad')
        assert all(views.showing(view) for view in views.layout.views)

    def test_the_cameras_keep_where_they_were_looking(self):
        """Switching arrangement is a change of window, not of where a designer is."""
        views = _views()
        views.show('quad')
        views.map.camera.view.pan(40.0, 0.0, views.size(views.map))
        centre = views.map.camera.view.centre
        views.show('map')
        views.arrange(*WINDOW)
        assert views.map.camera.view.centre == centre


class TestPlacingThemInTheWindow:
    def test_a_camera_is_told_the_size_of_its_own_tile(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        assert views.size(views.map) == (WINDOW[0] // 2, WINDOW[1] // 2)
        assert views.map.camera.viewport == views.size(views.map)

    def test_the_maps_own_pixels_are_measured_from_its_corner(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        left, bottom = views.map.rect[:2]
        assert views.map_local(left + 12, bottom + 7) == (12.0, 7.0)

    def test_a_view_the_layout_is_not_showing_is_measured_by_the_window(self):
        """So a view is framed for the window it is about to be shown in."""
        views = _views()
        assert views.size(views.elevations[0]) == WINDOW

    def test_the_active_view_can_have_the_window_to_itself(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        views.maximise(views.elevations[0])
        views.arrange(*WINDOW)
        assert views.size(views.elevations[0]) == WINDOW
        assert not views.showing(views.map)
        views.maximise(views.elevations[0])
        views.arrange(*WINDOW)
        assert views.showing(views.map)


class TestFramingTheLandscape:
    def test_the_landscape_is_on_screen_in_every_view(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        views.frame(LOW, HIGH, RELIEF)
        corners = [(x, y, z) for x in (LOW[0], HIGH[0]) for y in RELIEF
                   for z in (LOW[1], HIGH[1])]
        for view in views.layout.views:
            for corner in corners:
                assert np.all(np.abs(_ndc(view, corner)) <= 1.0 + 1e-5), (view.name, corner)

    def test_an_elevation_is_centred_on_the_middle_of_the_relief(self):
        views = _views()
        front = views.elevations[0]
        assert front.camera.view.centre[1] == pytest.approx(sum(RELIEF) / 2.0)

    def test_flat_ground_still_gives_an_elevation_something_to_show(self):
        """A landscape with no relief at all is a line; the view keeps a height."""
        views = EditorViews(MapView(span=EXTENT), OrbitView())
        views.arrange(*WINDOW)
        views.frame(LOW, HIGH, (12.0, 12.0))
        assert views.elevations[0].camera.view.span > 0.0
        assert views.elevations[0].camera.view.centre[1] == pytest.approx(12.0)


class TestWhoTheEventBelongsTo:
    def test_the_map_is_the_editors_to_drive(self):
        """The tools draw on the map, so the cameras leave that view alone."""
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        centre = views.map.camera.view.centre
        event = _Event(*_centre_of(views.map))
        assert views.view_for(event) is views.map
        assert not views.handle(event)
        assert not views.handle(_Event(*_centre_of(views.map), kind='mousemove'))
        assert views.map.camera.view.centre == centre

    def test_a_drag_in_an_elevation_pans_it(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        front = views.elevations[0]
        before = np.array(front.camera.view.centre)
        x, y = _centre_of(front)
        assert views.handle(_Event(x, y))
        assert views.handle(_Event(x + 30, y, kind='mousemove'))
        assert not np.allclose(front.camera.view.centre, before)

    def test_a_drag_in_the_angled_view_turns_the_camera(self):
        views = _views()
        views.show('split')
        views.arrange(*WINDOW)
        heading = views.angled.camera.view.heading
        x, y = _centre_of(views.angled)
        assert views.handle(_Event(x, y))
        assert views.handle(_Event(x + 30, y, kind='mousemove'))
        assert views.angled.camera.view.heading != heading

    def test_the_wheel_zooms_an_elevation_under_the_pointer(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        front = views.elevations[0]
        span = front.camera.view.span
        assert views.handle(_Event(*_centre_of(front), button=WHEEL_UP))
        assert front.camera.view.span < span

    def test_an_event_of_another_kind_is_nobodys(self):
        views = _views()
        assert not views.handle(_Event(10, 10, kind='keypress'))


class TestDrawingWhileTheMapIsOneTileOfFour:
    """The tools go on working on a map that no longer fills the window."""

    def _drawing(self, views):
        from OpenGLContext.edit.tools import ToolManager

        from glisteel_editor.controls import MapControls
        from glisteel_editor.editing import RouteEditor, RouteTool
        from glisteel_editor.project import Route
        route = Route(name='circuit', points=[])
        editor = RouteEditor(route)
        tools = ToolManager([RouteTool(editor=editor)])
        controls = MapControls(views.map.camera.view, tools, views.map_size,
                               editor=editor, locate=views.map_local)
        return controls, route

    def test_a_point_goes_where_the_pointer_was(self):
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        controls, route = self._drawing(views)
        x, y = _centre_of(views.map)
        controls.button(_Event(x, y))
        controls.button(_Event(x, y, state=0))
        assert route.points == [pytest.approx(views.map.camera.view.centre)]

    def test_the_same_pixel_means_something_else_in_another_arrangement(self):
        """Which is why the map is asked, rather than the window measured."""
        views = _views()
        views.show('quad')
        views.arrange(*WINDOW)
        controls, route = self._drawing(views)
        corner = (views.map.rect[0] + 20, views.map.rect[1] + 20)
        controls.button(_Event(*corner))
        controls.button(_Event(*corner, state=0))
        views.show('map')
        views.arrange(*WINDOW)
        controls.button(_Event(*corner))
        controls.button(_Event(*corner, state=0))
        assert route.points[0] != pytest.approx(route.points[1])
