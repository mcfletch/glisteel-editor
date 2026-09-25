"""The views the editor draws the landscape through.

Four cameras -- the map, two elevations and the angled view -- in the four
arrangements a designer can ask for. The arrangements themselves are the
engine's ``ViewSet``; what is tested here is which views the editor has, that
the map is left for the tools to drive, and that a landscape is fitted into all
of them including the height it rises through.

Headless: views, cameras and arithmetic, with no window and no GL.
"""
from __future__ import annotations

import numpy as np
import pytest
from OpenGLContext.edit.mapview import MapView, MapViewPlatform
from OpenGLContext.edit.orbitview import OrbitView, OrbitViewPlatform
from OpenGLContext.edit.tools import ToolManager
from OpenGLContext.events.mouseevents import WHEEL_UP
from OpenGLContext.multiview import OrthoViewPlatform

from glisteel_editor.controls import MapControls
from glisteel_editor.editing import RouteEditor, RouteTool
from glisteel_editor.project import Route
from glisteel_editor.views import LAYOUTS, editor_views, frame_landscape

WINDOW = (800, 600)
EXTENT = 2048.0
LOW, HIGH = (-EXTENT / 2.0, -EXTENT / 2.0), (EXTENT / 2.0, EXTENT / 2.0)
RELIEF = (0.0, 320.0)


def _views(**named):
    views = editor_views(MapView(centre=(0.0, 0.0), span=EXTENT),
                         OrbitView(centre=(0.0, 0.0)), **named)
    views.arrange(*WINDOW)
    frame_landscape(views, LOW, HIGH, RELIEF)
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
        assert [view.name for view in views.views] == ['map', 'front', 'left',
                                                       'angled']
        assert isinstance(views.view('map').camera, MapViewPlatform)
        assert isinstance(views.view('front').camera, OrthoViewPlatform)
        assert isinstance(views.view('angled').camera, OrbitViewPlatform)

    def test_the_elevations_can_be_chosen(self):
        views = _views(directions=('back', 'right'))
        assert [view.name for view in views.views[1:3]] == ['back', 'right']

    def test_three_elevations_is_not_an_editor_window(self):
        with pytest.raises(ValueError) as raised:
            editor_views(MapView(), OrbitView(), directions=('front', 'left', 'top'))
        assert 'two elevations' in str(raised.value)

    def test_the_elevations_clear_to_a_flat_colour_and_the_others_to_the_sky(self):
        views = _views()
        for name in ('front', 'left'):
            assert views.view(name).style.background not in (True, None)
        assert views.view('map').style.background is True
        assert views.view('angled').style.background is True

    def test_the_cameras_given_to_it_are_the_ones_it_draws_through(self):
        """The map camera is the editor's own, so the tools keep working on it."""
        plan, orbit = MapView(span=EXTENT), OrbitView()
        views = editor_views(plan, orbit)
        assert views.view('map').camera.view is plan
        assert views.view('angled').camera.view is orbit


class TestTheArrangements:
    def test_the_four_the_view_menu_offers(self):
        views = _views()
        assert list(views.arrangements) == list(LAYOUTS)

    def test_it_opens_on_the_map(self):
        views = _views()
        assert views.mode == 'map'
        assert views.layout.views == [views.view('map')]

    def test_the_split_puts_the_map_beside_the_angled_view(self):
        views = _views()
        views.show('split')
        assert [view.name for view in views.layout.views] == ['map', 'angled']

    def test_the_quad_is_the_map_two_elevations_and_the_angled_view(self):
        views = _views()
        views.show('quad')
        assert [view.name for view in views.layout.views] == ['map', 'front',
                                                              'left', 'angled']


class TestFramingTheLandscape:
    def test_the_landscape_is_on_screen_in_every_view(self):
        views = _views()
        views.show('quad')
        frame_landscape(views, LOW, HIGH, RELIEF)
        corners = [(x, y, z) for x in (LOW[0], HIGH[0]) for y in RELIEF
                   for z in (LOW[1], HIGH[1])]
        for view in views.layout.views:
            for corner in corners:
                assert np.all(np.abs(_ndc(view, corner)) <= 1.0 + 1e-5), (view.name, corner)

    def test_an_elevation_is_centred_on_the_middle_of_the_relief(self):
        views = _views()
        assert views.view('front').camera.view.centre[1] \
            == pytest.approx(sum(RELIEF) / 2.0)

    def test_the_map_is_framed_on_the_ground_it_covers(self):
        views = _views()
        assert views.view('map').camera.view.centre == pytest.approx((0.0, 0.0))

    def test_flat_ground_still_gives_an_elevation_something_to_show(self):
        """A landscape with no relief at all is a line; the view keeps a height."""
        views = _views()
        frame_landscape(views, LOW, HIGH, (12.0, 12.0))
        front = views.view('front')
        assert front.camera.view.span > 0.0
        assert front.camera.view.centre[1] == pytest.approx(12.0)


class TestWhoTheEventBelongsTo:
    def test_the_map_is_the_editors_to_drive(self):
        """The tools draw on the map, so the cameras leave that view alone."""
        views = _views()
        views.show('quad')
        plan = views.view('map')
        centre = plan.camera.view.centre
        event = _Event(*_centre_of(plan), button=2)
        assert views.view_for(event) is plan
        assert not views.handle(event)
        assert not views.handle(_Event(*_centre_of(plan), kind='mousemove'))
        assert plan.camera.view.centre == centre

    def test_a_right_drag_in_an_elevation_pans_it(self):
        views = _views()
        views.show('quad')
        front = views.view('front')
        before = np.array(front.camera.view.centre)
        x, y = _centre_of(front)
        assert views.handle(_Event(x, y, button=2))
        assert views.handle(_Event(x + 30, y, kind='mousemove'))
        assert not np.allclose(front.camera.view.centre, before)

    def test_a_right_drag_in_the_angled_view_turns_the_camera(self):
        views = _views()
        views.show('split')
        angled = views.view('angled')
        heading = angled.camera.view.heading
        x, y = _centre_of(angled)
        assert views.handle(_Event(x, y, button=2))
        assert views.handle(_Event(x + 30, y, kind='mousemove'))
        assert angled.camera.view.heading != heading

    def test_a_middle_drag_in_the_angled_view_carries_what_it_looks_at(self):
        """The left button is the tools', wherever the pointer also draws."""
        views = _views()
        views.show('split')
        angled = views.view('angled')
        heading = angled.camera.view.heading
        target = np.array(angled.camera.view.target())
        x, y = _centre_of(angled)
        assert views.handle(_Event(x, y, button=1))
        assert views.handle(_Event(x + 30, y, kind='mousemove'))
        assert angled.camera.view.heading == heading
        assert not np.allclose(angled.camera.view.target(), target)

    def test_the_wheel_zooms_an_elevation_under_the_pointer(self):
        views = _views()
        views.show('quad')
        front = views.view('front')
        span = front.camera.view.span
        assert views.handle(_Event(*_centre_of(front), button=WHEEL_UP))
        assert front.camera.view.span < span


class TestDrawingWhileTheMapIsOneTileOfFour:
    """The tools go on working on a map that no longer fills the window."""

    def _drawing(self, views):
        route = Route(name='circuit', points=[])
        editor = RouteEditor(route)
        tools = ToolManager([RouteTool(editor=editor)])
        plan = views.view('map')
        controls = MapControls(
            plan.camera.view, tools, lambda: views.size(plan), editor=editor,
            locate=lambda x, y: views.local(plan, x, y))
        return controls, route

    def test_a_point_goes_where_the_pointer_was(self):
        views = _views()
        views.show('quad')
        controls, route = self._drawing(views)
        plan = views.view('map')
        x, y = _centre_of(plan)
        controls.button(_Event(x, y))
        controls.button(_Event(x, y, state=0))
        assert route.points == [pytest.approx(plan.camera.view.centre)]

    def test_the_same_pixel_means_something_else_in_another_arrangement(self):
        """Which is why the map is asked, rather than the window measured."""
        views = _views()
        views.show('quad')
        controls, route = self._drawing(views)
        plan = views.view('map')
        corner = (plan.rect[0] + 20, plan.rect[1] + 20)
        controls.button(_Event(*corner))
        controls.button(_Event(*corner, state=0))
        views.show('map')
        controls.button(_Event(*corner))
        controls.button(_Event(*corner, state=0))
        assert route.points[0] != pytest.approx(route.points[1])
