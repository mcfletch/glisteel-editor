"""Banked corners, as the editor shows them and as a baked world gets them.

The road generator decides how far each corner leans
(``OpenGLContext_editor.world.road``). What is here is the editor's end of it:
that the preview draws the road the bake will build rather than a flat one, and
that a project's world carries the lean out to the tileset.
"""
import numpy as np

from glisteel_editor.project import Landscape, Project, Route


def _ring(radius=260.0, count=24):
    """A closed circuit small enough that its corners have to lean."""
    angle = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    return [(float(radius * np.cos(a)), float(radius * np.sin(a)))
            for a in angle]


def _project():
    return Project(name='Test', landscape=Landscape(extent=2048.0, seed=11),
                   routes=[Route(name='circuit', closed=True,
                                 points=_ring())])


class TestTheRoadTheEditorShows:
    def test_its_corners_lean(self) -> None:
        assert np.abs(_project().world().circuit().bank).max() > 0.05

    def test_the_preview_draws_the_lean_rather_than_a_flat_road(self) -> None:
        from glisteel_editor.scene import MapScene
        scene = MapScene(_project(), resolution=33)
        road = scene.road()
        assert road is not None
        path = scene.world().circuit()
        ring = len(path.profile.section())
        rings = np.asarray(road.geometry.positions, dtype='d').reshape(-1, ring, 3)
        # One cut across a banked road has its two ends a long way apart in
        # height; across a flat one they are level whatever the road is doing.
        tilt = np.abs(rings[:, 0, 1] - rings[:, -1, 1])
        lean = float(np.abs(path.bank).max())
        assert tilt.max() > lean * path.profile.total_width * 0.9
