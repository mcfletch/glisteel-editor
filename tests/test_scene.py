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
        see what the line is doing to the landscape.

        Along the road the generator built rather than at a point the designer
        drew: a corner is *rounded* when the road is built, so a drawn vertex
        is beside the road rather than on it, and where the alignment happens
        to sit on the ground there is nothing to cut.
        """
        scene = _scene()
        line = scene.world().circuit().points[::17, [0, 2]]
        moved = max(abs(scene.height_at(x, z) - scene.natural_height_at(x, z))
                    for x, z in line)
        assert moved > 0.1


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


class TestReadingTheRelief:
    """A plan view lit from straight overhead is flat; a shaded one is a map."""

    def _colours(self, scene):
        return np.asarray(scene.ground().geometry.colors, 'd')

    def test_shading_varies_with_which_way_the_ground_faces(self) -> None:
        scene = _scene()
        scene.hillshade = True
        shaded = self._colours(scene)
        scene.reset()
        scene.hillshade = False
        plain = self._colours(scene)
        assert shaded.std() > plain.std()

    def test_shaded_ground_is_drawn_unlit(self) -> None:
        """The shading is in the vertex colours, so a light would double it."""
        scene = _scene()
        scene.hillshade = True
        assert scene.ground().appearance.material.unlit

    def test_unshaded_ground_is_lit_as_before(self) -> None:
        scene = _scene()
        scene.hillshade = False
        assert not scene.ground().appearance.material.unlit

    def test_turning_it_on_rebuilds_the_land(self) -> None:
        scene = _scene()
        scene.hillshade = False
        before = scene.ground()
        scene.hillshade = True
        assert scene.ground() is not before


class TestTheContours:
    def test_one_line_set_per_elevation(self) -> None:
        scene = _scene()
        scene.contour_interval = 50.0
        levels = _contour_levels(scene)
        assert len(scene.contours().children) == len(levels)

    def test_they_are_drawn_at_the_chosen_interval(self) -> None:
        scene = _scene()
        scene.contour_interval = 50.0
        spacing = np.diff(_contour_levels(scene))
        assert len(spacing) > 1
        assert np.allclose(spacing, 50.0, atol=1e-6)

    def test_a_finer_interval_draws_more_of_them(self) -> None:
        scene = _scene()
        scene.contour_interval = 25.0
        fine = len(scene.contours().children)
        scene.contour_interval = 100.0
        coarse = len(scene.contours().children)
        assert fine > coarse

    def test_they_float_above_the_ground_they_describe(self) -> None:
        """Or the surface they are drawn on buries them."""
        scene = _scene()
        points = _positions_of_lines(scene.contours())
        for x, y, z in points[:40]:
            assert y > scene.height_at(x, z)

    def test_they_are_not_in_the_scene_when_they_are_turned_off(self) -> None:
        scene = _scene()
        scene.show_contours = False
        assert scene.contours() is None

    def test_they_are_built_once_and_kept(self) -> None:
        scene = _scene()
        assert scene.contours() is scene.contours()

    def test_changing_the_interval_rebuilds_them(self) -> None:
        scene = _scene()
        before = scene.contours()
        scene.contour_interval = 12.5
        assert scene.contours() is not before

    def test_the_whole_scene_carries_them(self) -> None:
        scene = _scene()
        with_them = _count_lines(scene.build(2.0))
        scene.show_contours = False
        without = _count_lines(scene.build(2.0))
        assert with_them > without


def _contour_levels(scene):
    """The elevations a scene's contours are drawn for, in order."""
    from OpenGLContext_editor.world.contours import contours_of
    return sorted(contour.elevation for contour in contours_of(
        scene.world().natural(), extent=scene.project.landscape.extent,
        interval=scene.contour_interval, resolution=257))


def _positions_of_lines(node):
    from OpenGLContext.scenegraph.basenodes import IndexedLineSet
    from OpenGLContext.scenegraph.shape import Shape
    found = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, Shape) and isinstance(current.geometry,
                                                     IndexedLineSet):
            found.extend(np.asarray(current.geometry.coord.point, 'd'))
        stack.extend(getattr(current, 'children', None) or ())
    return np.asarray(found) if found else np.zeros((0, 3))


def _count_lines(node):
    return len(_positions_of_lines(node))


class TestHowCloselyToDescribeTheLand:
    """A contour interval that suits rolling hills hatches a mountain range."""

    def _scene_on(self, name):
        from OpenGLContext_editor.world.presets import PresetBase

        from glisteel_editor.project import new_project
        project = new_project(extent=4096.0, base=PresetBase(name=name))
        return MapScene(project, resolution=33)

    def test_taller_country_is_described_more_coarsely(self) -> None:
        assert self._scene_on('mountains').suggested_interval() \
            > self._scene_on('hills').suggested_interval()

    def test_the_answer_is_one_a_designer_can_also_choose(self) -> None:
        from glisteel_editor.app import CONTOUR_INTERVALS
        for name in ('mountains', 'canyon', 'lakes', 'hills'):
            assert self._scene_on(name).suggested_interval() in CONTOUR_INTERVALS

    def test_no_landscape_is_described_by_more_lines_than_can_be_read(self) -> None:
        from OpenGLContext_editor.world.contours import contour_levels
        for name in ('mountains', 'canyon', 'lakes', 'hills'):
            scene = self._scene_on(name)
            low, high = scene.relief()
            levels = contour_levels(low, high, scene.suggested_interval())
            assert len(levels) <= MapScene.READABLE_CONTOURS

    def test_the_relief_is_what_the_landscape_actually_does(self) -> None:
        low, high = self._scene_on('hills').relief()
        assert high > low
        assert high - low < 200.0


class TestTheBrush:
    """Sculpting with an invisible brush is guessing."""

    def test_the_ring_is_where_the_brush_is(self) -> None:
        scene = _scene()
        ring = _positions_of_lines(scene.brush((100.0, -50.0), 80.0))
        assert ring[:, 0].mean() == pytest.approx(100.0, abs=2.0)
        assert ring[:, 2].mean() == pytest.approx(-50.0, abs=2.0)

    def test_it_is_as_wide_as_the_brush(self) -> None:
        scene = _scene()
        ring = _positions_of_lines(scene.brush((0.0, 0.0), 120.0))
        assert np.hypot(ring[:, 0], ring[:, 2]).mean() \
            == pytest.approx(120.0, abs=2.0)

    def test_it_closes(self) -> None:
        scene = _scene()
        ring = _positions_of_lines(scene.brush((0.0, 0.0), 60.0))
        assert np.allclose(ring[0], ring[-1], atol=1e-6)

    def test_it_follows_the_ground_it_is_over(self) -> None:
        """A ring at one height cuts into a hillside and is half-buried."""
        scene = _scene()
        ring = _positions_of_lines(scene.brush((0.0, 0.0), 400.0))
        assert ring[:, 1].std() > 1.0

    def test_the_scene_draws_it_when_there_is_one(self) -> None:
        scene = _scene()
        without = _count_lines(scene.build(2.0))
        with_it = _count_lines(scene.build(2.0, brush=((0.0, 0.0), 100.0)))
        assert with_it > without

    def test_no_brush_draws_no_ring(self) -> None:
        scene = _scene()
        assert scene.build(2.0, brush=None) is not None


class TestTheWater:
    def _watered(self):
        from OpenGLContext_editor.world.hydrology import Spring
        project = _project()
        project.landscape.springs.append(Spring(at=(-800.0, 700.0)))
        return MapScene(project, resolution=33)

    def test_a_landscape_with_no_water_draws_none(self) -> None:
        assert _scene().water() is None

    def test_a_spring_puts_a_river_on_the_map(self) -> None:
        """A surface with width to it, not a line standing for one."""
        scene = self._watered()
        assert scene.water() is not None
        points = _positions(scene.water())
        assert len(points) > 6

    def test_the_river_lies_on_the_ground_the_map_draws(self) -> None:
        """Not in the bed the baked world will have. The plan view meshes the
        landscape at a few hundred samples across kilometres and draws straight
        lines between them, so over a valley it passes above the surface it
        stands for -- and a river at its true depth is inside the ground."""
        scene = self._watered()
        points = _positions(scene.water())[:20]
        for x, y, z in points:
            assert y > float(scene.drawn_height(x, z))
            assert y < float(scene.drawn_height(x, z)) + 10.0

    def test_it_is_drawn_to_be_read(self) -> None:
        """Map water, not the water a baked world gets: real water is nearly
        black and borrows its brightness, which over a snowfield at a
        kilometre's range is a film nobody can see."""
        scene = self._watered()
        rivers = [child for child in scene.water().children
                  if getattr(child, 'appearance', None) is not None]
        assert rivers
        material = rivers[0].appearance.material
        assert material.unlit
        assert material.baseColor[2] > material.baseColor[0]

    def test_the_spring_is_marked_where_it_was_put(self) -> None:
        from OpenGLContext.scenegraph.transform import Transform
        scene = self._watered()
        marks = [np.asarray(node.translation, 'd')
                 for node in scene.water().children
                 if isinstance(node, Transform)]
        assert marks
        assert min(abs(mark[0] - (-800.0)) for mark in marks) < 1.0
        assert min(abs(mark[2] - 700.0) for mark in marks) < 1.0

    def test_the_whole_scene_carries_it(self) -> None:
        scene = self._watered()
        assert len(_positions(scene.build(2.0))) \
            > len(_positions(_scene().build(2.0)))

    def test_it_is_built_once_and_kept(self) -> None:
        scene = self._watered()
        assert scene.water() is scene.water()

    def test_a_new_spring_redraws_it(self) -> None:
        from OpenGLContext_editor.world.hydrology import Spring
        scene = self._watered()
        before = scene.water()
        scene.project.landscape.springs.append(Spring(at=(-700.0, 640.0)))
        scene.water_changed()
        assert scene.water() is not before


class TestTheStartLine:
    def test_it_is_drawn_across_the_route_where_the_lap_begins(self) -> None:
        scene = _scene()
        scene.project.route().start = 1
        bar = _positions_of_lines(scene.start_mark(2.0))
        where = scene.project.route().points[1]
        assert np.abs(bar[:, 0].mean() - where[0]) < 5.0
        assert np.abs(bar[:, 2].mean() - where[1]) < 5.0

    def test_it_lies_across_the_line_rather_than_along_it(self) -> None:
        """A bar along the road is a road marking, not a start line.

        On a straight, where which way the road runs is not a question.
        """
        project = _project(points=[(-400.0, 0.0), (0.0, 0.0), (400.0, 0.0)])
        project.route().closed = False
        project.route().start = 1
        bar = _positions_of_lines(MapScene(project, resolution=33).start_mark(2.0))
        across = bar[-1, [0, 2]] - bar[0, [0, 2]]
        across = across / np.linalg.norm(across)
        assert abs(float(np.dot(np.array([1.0, 0.0]), across))) < 0.05

    def test_a_route_with_no_line_yet_has_none(self) -> None:
        project = _project(points=[])
        assert MapScene(project, resolution=33).start_mark(2.0) is None

    def test_the_whole_scene_carries_it(self) -> None:
        scene = _scene()
        assert _count_lines(scene.build(2.0)) > _count_lines(
            MapScene(_project(points=[]), resolution=33).build(2.0))
