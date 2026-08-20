"""What a redraw of the map costs, and what it should not.

``_rebuild`` runs on every pointer movement while a designer drags a point, so
what one costs is what dragging feels like. Three things made it expensive, and
none of them was the drawing: a whole world built to read one number off it, the
ground sampled one point at a time, and the two answers that are ``None`` while
a line is too short to be a road worked out again every time.
"""
import numpy as np
import pytest

from glisteel_editor.project import Project, new_project
from glisteel_editor.scene import LIFT, MapScene


def _project(points=None):
    if points is None:
        angle = np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False)
        points = [(float(600.0 * np.cos(a)), float(600.0 * np.sin(a)))
                  for a in angle]
    return new_project(extent=2048.0, points=points)


def _warm(scene):
    """A scene with every cache primed, as a redraw mid-drag finds one."""
    scene.build(1.0, None)
    return scene


class _CountedWorlds:
    """Counts how many whole worlds a block of code builds."""

    def __enter__(self):
        self.built = 0
        self._real = Project.world
        Project.world = lambda one: (self._count(), self._real(one))[1]
        return self

    def _count(self):
        self.built += 1

    def __exit__(self, *exc):
        Project.world = self._real
        return False


class TestARedrawDoesNotBuildAWorld:
    """The scene keeps the world it is drawing; nothing may go round it."""

    def test_a_warm_redraw_builds_none(self) -> None:
        scene = _warm(MapScene(_project()))
        with _CountedWorlds() as counted:
            scene.build(1.0, None)
        assert counted.built == 0, 'built %d worlds' % counted.built

    def test_the_start_mark_alone_builds_none(self) -> None:
        scene = _warm(MapScene(_project()))
        with _CountedWorlds() as counted:
            scene.start_mark(1.0)
        assert counted.built == 0

    def test_it_still_draws_the_start_bar(self) -> None:
        scene = _warm(MapScene(_project()))
        assert scene.start_mark(1.0) is not None

    def test_a_line_too_short_for_a_road_still_gets_one(self) -> None:
        scene = MapScene(_project(points=[(0.0, 0.0)]))
        assert scene.start_mark(2.0) is not None


class TestTheGroundIsSampledInOneGo:
    """The height function is vectorised; the contours already use it that way."""

    def _asked(self, scene, call):
        calls = []
        real = scene.world().height_fn()

        def counting(x, z):
            calls.append(np.size(np.asarray(x)))
            return real(x, z)
        scene.world().height_fn = lambda: counting
        try:
            call()
        finally:
            del scene.world().height_fn
        return calls

    def test_the_line_is_sampled_once_for_all_its_points(self) -> None:
        scene = _warm(MapScene(_project()))
        calls = self._asked(scene, scene.guide)
        assert len(calls) <= 1, 'sampled the ground %d times' % len(calls)

    def test_the_markers_are_too(self) -> None:
        scene = _warm(MapScene(_project()))
        calls = self._asked(scene, lambda: scene.markers(1.0))
        assert len(calls) <= 1, 'sampled the ground %d times' % len(calls)

    def test_the_line_is_still_drawn_on_the_ground(self) -> None:
        project = _project()
        scene = _warm(MapScene(project))
        guide = scene.guide()
        points = np.asarray(guide.geometry.coord.point, dtype='d')
        assert len(points) == len(project.routes[0].points)
        for (x, _y, z), (wx, wz) in zip(points, project.routes[0].points,
                                        strict=True):
            assert x == pytest.approx(wx)
            assert z == pytest.approx(wz)

    def test_every_point_is_at_the_height_of_the_ground_under_it(self) -> None:
        project = _project()
        scene = _warm(MapScene(project))
        points = np.asarray(scene.guide().geometry.coord.point, dtype='d')
        for x, y, z in points:
            # The scenegraph keeps coordinates as float32.
            assert y == pytest.approx(scene.height_at(x, z) + LIFT, abs=1e-3)

    def test_the_markers_are_where_the_points_are(self) -> None:
        project = _project()
        scene = _warm(MapScene(project))
        marks = scene.markers(1.0).children
        assert len(marks) == len(project.routes[0].points)
        for mark, (wx, wz) in zip(marks, project.routes[0].points, strict=True):
            assert mark.translation[0] == pytest.approx(wx)
            assert mark.translation[2] == pytest.approx(wz)


class TestWhatIsNotThereIsOnlyWorkedOutOnce:
    """A route too short to be a road answers None, and that is an answer."""

    def test_what_carries_the_road_is_only_worked_out_once(self) -> None:
        """Whatever the answer, including when the answer is nothing.

        ``None`` is a perfectly good answer -- a circuit over flat ground needs
        no bridge and no bore -- and a cache that could not tell that from "not
        worked out yet" settled the whole alignment again on every redraw.
        """
        scene = _warm(MapScene(_project()))
        scene.structures()
        asked = []
        real = scene.world().circuit
        scene.world().circuit = lambda: (asked.append(1), real())[1]
        try:
            scene.structures()
            scene.structures()
        finally:
            del scene.world().circuit
        assert not asked, 'settled the alignment %d times for nothing' % len(asked)

    def test_a_line_too_short_for_a_road_is_not_settled_either(self) -> None:
        scene = MapScene(_project(points=[(0.0, 0.0)]))
        scene.build(1.0, None)
        asked = []
        real = scene.world().circuit
        scene.world().circuit = lambda: (asked.append(1), real())[1]
        try:
            scene.road()
            scene.structures()
        finally:
            del scene.world().circuit
        assert not asked

    def test_a_road_appearing_is_still_noticed(self) -> None:
        project = _project(points=[(0.0, 0.0)])
        scene = MapScene(project)
        assert scene.road() is None
        project.routes[0].points.extend([(200.0, 0.0), (400.0, 100.0)])
        scene.route_changed()
        assert scene.road() is not None
