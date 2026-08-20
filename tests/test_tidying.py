"""Small things the P3 clean-up fixes, and behaviour it must not change.

A marker drawn at a fixed size in metres, a guard that guards nothing, and a
history kept as a tuple read by index: each is small, and each is the kind of
thing that is wrong in a way nobody notices until it matters.
"""
import pytest
from OpenGLContext_editor.world.hydrology import Spring

from glisteel_editor.editing import RouteEditor
from glisteel_editor.project import Route, new_project
from glisteel_editor.scene import SPRING_PIXELS, MapScene


class TestASpringIsTheSameSizeToClickAtAnyZoom:
    """As the control points are, and for the same reason: a marker fixed in
    metres disappears at the scale a whole landscape is drawn at."""

    def _sizes(self, metres_per_pixel):
        project = new_project(extent=2048.0)
        project.landscape.springs.append(Spring(at=(100.0, -200.0)))
        scene = MapScene(project)
        group = scene.water(metres_per_pixel)
        marks = [one for one in group.children
                 if getattr(one, 'translation', None) is not None]
        return [one.children[0].geometry.size[0] for one in marks]

    def test_zoomed_out_it_is_drawn_larger(self) -> None:
        close, far = self._sizes(1.0), self._sizes(8.0)
        assert far[0] > close[0]

    def test_it_is_the_pixel_size_it_says(self) -> None:
        assert self._sizes(3.0)[0] == pytest.approx(3.0 * SPRING_PIXELS)

    def test_the_whole_scene_passes_the_zoom_through(self) -> None:
        project = new_project(extent=2048.0)
        project.landscape.springs.append(Spring(at=(0.0, 0.0)))
        scene = MapScene(project)
        scene.build(6.0, None)
        group = scene.water(6.0)
        marks = [one for one in group.children
                 if getattr(one, 'translation', None) is not None]
        assert marks[0].children[0].geometry.size[0] == \
            pytest.approx(6.0 * SPRING_PIXELS)


class TestARouteDrivenTheOtherWayRound:
    """``plan()`` hands the generator the points in the order they are driven."""

    def test_two_points_swap_ends(self) -> None:
        route = Route(name='road', points=[(0.0, 0.0), (100.0, 0.0)],
                      closed=False, reversed=True)
        assert [tuple(one) for one in route.plan()] == [(100.0, 0.0), (0.0, 0.0)]

    def test_an_open_road_is_driven_from_its_other_end(self) -> None:
        route = Route(name='road', closed=False, reversed=True,
                      points=[(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)])
        assert tuple(route.plan()[0]) == (200.0, 0.0)
        assert tuple(route.plan()[-1]) == (0.0, 0.0)

    def test_a_circuit_keeps_where_it_begins(self) -> None:
        """A lap starts where it starts; only the direction turns round."""
        route = Route(name='circuit', closed=True, reversed=True,
                      points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0),
                              (0.0, 100.0)])
        assert tuple(route.plan()[0]) == (0.0, 0.0)
        assert tuple(route.plan()[1]) == (0.0, 100.0)

    def test_the_length_is_the_same_either_way(self) -> None:
        points = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
        one = Route(name='r', points=list(points), closed=False)
        other = Route(name='r', points=list(points), closed=False, reversed=True)
        assert one.length() == pytest.approx(other.length())


class TestTakingBackAChangeToTheLine:
    """The history holds a named state rather than a tuple read by index."""

    def _editor(self):
        return RouteEditor(Route(name='circuit', closed=True,
                                 points=[(0.0, 0.0), (100.0, 0.0)]))

    def test_it_puts_back_everything_a_change_touched(self) -> None:
        editor = self._editor()
        editor.close_route(False)
        editor.start_at(1)
        editor.turn_round()
        editor.append((200.0, 50.0))
        for _ in range(4):
            editor.undo()
        assert editor.route.points == [(0.0, 0.0), (100.0, 0.0)]
        assert editor.route.closed is True
        assert editor.route.start == 0
        assert editor.route.reversed is False

    def test_the_state_says_what_it_holds(self) -> None:
        state = self._editor()._state()
        assert state.points == [(0.0, 0.0), (100.0, 0.0)]
        assert state.closed is True
        assert state.start == 0
        assert state.reversed is False

    def test_redo_puts_it_back_again(self) -> None:
        editor = self._editor()
        editor.append((200.0, 50.0))
        editor.undo()
        editor.redo()
        assert len(editor.route.points) == 3
