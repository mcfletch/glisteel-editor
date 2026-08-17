"""What the plan view draws: the land, the line, and the road it makes.

Headless. Building geometry is arithmetic over a height function and a list of
points, so what a scene *is* can be asserted without drawing it: how many nodes,
where they are, and that they change when the project does.
"""
import numpy as np
import pytest

from glisteel_editor.project import Landscape, Project, Route
from glisteel_editor.scene import MapScene


def _project(points=((-400.0, -300.0), (400.0, -300.0), (400.0, 300.0),
                     (-400.0, 300.0))):
    return Project(name='Test', landscape=Landscape(extent=2048.0, seed=11),
                   routes=[Route(name='circuit', closed=True,
                                 points=[tuple(p) for p in points])])


def _scene(project=None, **named):
    named.setdefault('resolution', 33)
    return MapScene(project or _project(), **named)


def _positions(node):
    """Every vertex a node's subtree holds, in its own coordinates."""
    from OpenGLContext.scenegraph.shape import Shape
    found = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, Shape) and current.geometry is not None:
            points = getattr(current.geometry, 'positions', None)
            if points is not None:
                found.append(np.asarray(points, 'd'))
        stack.extend(getattr(current, 'children', None) or ())
    return np.vstack(found) if found else np.zeros((0, 3))


class TestTheLand:
    def test_it_meshes_the_whole_landscape(self) -> None:
        points = _positions(_scene().ground())
        half = 2048.0 / 2.0
        assert points[:, 0].min() == pytest.approx(-half, abs=1.0)
        assert points[:, 0].max() == pytest.approx(half, abs=1.0)

    def test_it_has_relief(self) -> None:
        points = _positions(_scene().ground())
        assert points[:, 1].max() - points[:, 1].min() > 20.0

    def test_a_coarser_scene_is_cheaper(self) -> None:
        assert len(_positions(_scene(resolution=17).ground())) \
            < len(_positions(_scene(resolution=65).ground()))

    def test_the_ground_is_built_once_and_kept(self) -> None:
        """It is a second of arithmetic; rebuilding it per frame is a slideshow."""
        scene = _scene()
        assert scene.ground() is scene.ground()

    def test_a_new_landscape_is_a_new_ground(self) -> None:
        scene = _scene()
        before = scene.ground()
        scene.project.landscape = Landscape(extent=1024.0, seed=3)
        scene.reset()
        assert scene.ground() is not before

    def test_the_ground_it_shows_is_the_ground_that_bakes(self) -> None:
        """Earthworks included: a designer who cannot see the cutting cannot
        see what the line is doing to the landscape."""
        scene = _scene()
        route = scene.project.routes[0]
        on_road = np.asarray(route.points[0], 'd')
        height = scene.height_at(on_road[0], on_road[1])
        natural = scene.natural_height_at(on_road[0], on_road[1])
        assert height != pytest.approx(natural, abs=1e-6)


class TestTheLineTheDesignerDrew:
    def test_there_is_a_marker_for_every_point(self) -> None:
        scene = _scene()
        assert len(scene.markers(metres_per_pixel=1.0).children) == 4

    def test_each_marker_stands_where_its_point_is(self) -> None:
        scene = _scene()
        markers = scene.markers(metres_per_pixel=1.0)
        placed = sorted((round(float(m.translation[0])),
                         round(float(m.translation[2]))) for m in markers.children)
        assert placed == sorted((round(x), round(z))
                                for x, z in scene.project.routes[0].points)

    def test_a_marker_sits_on_the_ground_under_it(self) -> None:
        scene = _scene()
        marker = scene.markers(metres_per_pixel=1.0).children[0]
        x, z = float(marker.translation[0]), float(marker.translation[2])
        assert float(marker.translation[1]) >= scene.height_at(x, z)

    def test_markers_are_a_size_on_the_screen_not_on_the_ground(self) -> None:
        """Zoom out and a marker stays the same handful of pixels, or it
        vanishes at the scale a whole circuit is drawn at."""
        scene = _scene()
        near = scene.markers(metres_per_pixel=0.5).children[0]
        far = scene.markers(metres_per_pixel=4.0).children[0]
        assert float(far.children[0].geometry.size[0]) > \
            float(near.children[0].geometry.size[0])

    def test_the_point_under_the_pointer_is_marked_out(self) -> None:
        scene = _scene()
        plain = scene.markers(metres_per_pixel=1.0, hovered=None).children[1]
        lit = scene.markers(metres_per_pixel=1.0, hovered=1).children[1]
        assert tuple(lit.children[0].appearance.material.baseColor) \
            != tuple(plain.children[0].appearance.material.baseColor)

    def test_a_route_with_nothing_in_it_draws_nothing(self) -> None:
        project = _project(points=())
        assert not _scene(project).markers(metres_per_pixel=1.0).children

    def test_the_line_joins_the_points_in_order(self) -> None:
        scene = _scene()
        line = scene.guide()
        coordinates = np.asarray(line.geometry.coord.point, 'd')
        assert len(coordinates) == 4
        assert np.allclose(coordinates[0][[0, 2]], (-400.0, -300.0))

    def test_a_closed_route_s_line_comes_home(self) -> None:
        scene = _scene()
        index = list(scene.guide().geometry.coordIndex)
        assert index[:5] == [0, 1, 2, 3, 0]

    def test_an_open_one_does_not(self) -> None:
        project = _project()
        project.routes[0].closed = False
        index = list(_scene(project).guide().geometry.coordIndex)
        assert index[:4] == [0, 1, 2, 3]
        assert 0 not in index[1:4]

    def test_a_line_of_one_point_is_not_a_line(self) -> None:
        assert _scene(_project(points=[(0.0, 0.0)])).guide() is None


class TestTheRoadItMakes:
    def test_a_drawn_circuit_becomes_a_road(self) -> None:
        assert _scene().road() is not None

    def test_the_road_follows_the_line(self) -> None:
        scene = _scene()
        points = _positions(scene.road())
        assert points[:, 0].max() > 380.0
        assert points[:, 0].min() < -380.0

    def test_the_road_is_built_once_and_kept(self) -> None:
        scene = _scene()
        assert scene.road() is scene.road()

    def test_a_changed_line_is_a_changed_road(self) -> None:
        scene = _scene()
        before = scene.road()
        scene.project.routes[0].points[0] = (-600.0, -500.0)
        scene.reset()
        assert scene.road() is not before

    def test_too_short_a_line_makes_no_road(self) -> None:
        assert _scene(_project(points=[(0.0, 0.0)])).road() is None


class TestWhatGoesInTheWindow:
    def test_the_scene_holds_the_land_the_line_and_the_road(self) -> None:
        scene = _scene()
        group = scene.build(metres_per_pixel=1.0)
        assert scene.ground() in list(group.children)
        assert scene.road() in list(group.children)

    def test_it_can_be_rebuilt_without_re_meshing_the_land(self) -> None:
        scene = _scene()
        ground = scene.ground()
        scene.build(metres_per_pixel=1.0)
        scene.build(metres_per_pixel=2.0)
        assert scene.ground() is ground


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestWhereTheRoadIsCarried:
    """A plan view that draws only the carriageway tells a designer nothing
    about the third of the line that is a viaduct or a bore -- and where a road
    is carried is the most expensive decision the line makes."""

    def _scene(self, radius=520.0, points=14):
        import math

        from glisteel_editor.project import Landscape, Project, Route
        from glisteel_editor.scene import MapScene
        plan = [(radius * math.cos(2 * math.pi * i / points),
                 radius * 0.75 * math.sin(2 * math.pi * i / points))
                for i in range(points)]
        project = Project(name='drawn',
                          landscape=Landscape(extent=2048.0, seed=11,
                                              resolution=17),
                          routes=[Route(name='circuit', closed=True,
                                        points=plan)])
        return MapScene(project)

    def test_the_structures_are_drawn(self) -> None:
        found = self._scene().structures()
        assert found is not None

    def test_a_line_too_short_to_be_a_road_has_none(self) -> None:
        from glisteel_editor.project import Landscape, Project, Route
        from glisteel_editor.scene import MapScene
        project = Project(name='x', landscape=Landscape(extent=1024.0),
                          routes=[Route(name='c', points=[(0.0, 0.0)])])
        assert MapScene(project).structures() is None

    def test_each_kind_has_its_own_colour(self) -> None:
        """A deck and a bore are two different things to a designer."""
        from glisteel_editor.scene import STRUCTURE_COLOURS
        scene = self._scene()
        mesh = scene.structures().geometry
        colours = {tuple(round(float(v), 3) for v in one[:3])
                   for one in mesh.colors}
        wanted = {tuple(round(float(v), 3) for v in STRUCTURE_COLOURS[kind])
                  for kind in scene.structure_counts()}
        assert colours == wanted

    def test_they_are_wide_enough_to_see_at_map_scale(self) -> None:
        """A road drawn at a kilometre a screen is a hairline."""
        from glisteel_editor.scene import STRUCTURE_WIDTH
        scene = self._scene()
        assert STRUCTURE_WIDTH > 1.0
        assert len(scene.structures().geometry.positions) > 8

    def test_they_are_part_of_what_the_map_draws(self) -> None:
        scene = self._scene()
        drawn = list(scene.build(metres_per_pixel=2.0).children)
        assert scene.structures() in drawn

    def test_the_route_reports_what_is_on_it(self) -> None:
        counts = self._scene().structure_counts()
        assert sum(counts.values()) > 0
        assert set(counts) <= {'bridge', 'tunnel', 'causeway'}

    def test_a_flat_route_reports_none(self) -> None:
        from glisteel_editor.project import Landscape, Project, Route
        from glisteel_editor.scene import MapScene
        project = Project(name='x', landscape=Landscape(extent=1024.0),
                          routes=[Route(name='c', points=[(0.0, 0.0)])])
        assert MapScene(project).structure_counts() == {}
