"""The whole point: a line drawn on a map becomes a world a game can drive.

Slow -- it bakes a small world -- but it is the only test that says the editor
does what it is for. Everything between the pointer and the tileset is exercised
here: the project, the road generator, the earthworks, the baker, and the
tileset a game reads the circuit back out of.
"""
import json
import os

import numpy as np
import pytest
import support

#: Every test here bakes, and a bake is seconds rather than milliseconds. They
#: are marked so that a working loop can be ``-m "not slow"`` and a full run is
#: still the default.
pytestmark = pytest.mark.slow


def _drawn():
    """A circuit as a designer would have clicked it out.

    Small and coarse -- a kilometre across, sampled at seventeen points a side
    -- because what is being asserted is that a bake produces a drivable world,
    not how finely it can produce one.
    """
    return support.project(support.ring_points(radius=420.0, count=16,
                                               flatten=0.7),
                           name='Drawn', extent=1024.0, resolution=17)


def _bake(project, directory, depth=2, **named):
    from OpenGLContext_editor.bake.driver import bake_world
    result = bake_world(project.world().layers(), directory, depth=depth,
                        **named)
    with open(result.tileset) as handle:
        return result, json.load(handle)


@pytest.fixture(scope='module')
def baked(tmp_path_factory):
    """One bake, shared: it is seconds of work and nothing here changes it."""
    from OpenGLContext_editor.world.procedural import CREDITS
    project = _drawn()
    result, document = _bake(project, str(tmp_path_factory.mktemp('world')),
                             credits=list(CREDITS))
    return project, result, document


class TestWhatComesOut:
    def test_a_tileset_is_written(self, baked) -> None:
        _project, result, _document = baked
        assert os.path.exists(result.tileset)

    def test_it_holds_tiles(self, baked) -> None:
        _project, result, _document = baked
        assert result.tiles > 1

    def test_every_tile_it_names_is_there(self, baked) -> None:
        _project, result, document = baked
        for uri in _uris(document['root']):
            assert os.path.exists(os.path.join(result.directory, uri))

    def test_the_road_surface_is_written_once_beside_it(self, baked) -> None:
        _project, result, _document = baked
        assert any(name.endswith('.png') for name in result.assets)

    def test_it_says_where_the_landscape_came_from(self, baked) -> None:
        _project, result, document = baked
        assert document['asset'].get('copyright')
        assert os.path.exists(os.path.join(result.directory, 'CREDITS.txt'))


class TestTheCircuitTheGameGetsBack:
    def test_the_route_travels_with_the_world(self, baked) -> None:
        _project, _result, document = baked
        assert document['extras']['roads']

    def test_it_is_the_line_that_was_drawn(self, baked) -> None:
        """Not the shipped world's own circuit: the one in the project."""
        project, _result, document = baked
        road = document['extras']['roads'][0]
        drawn = project.routes[0]
        assert road['closed'] is True
        assert road['length'] == pytest.approx(drawn.length(), rel=0.15)

    def test_it_stays_inside_the_landscape(self, baked) -> None:
        project, _result, document = baked
        line = np.asarray(document['extras']['roads'][0]['centreline'], 'd')
        half = project.landscape.extent / 2.0
        assert abs(line[:, 0]).max() <= half
        assert abs(line[:, 2]).max() <= half

    def test_a_game_can_read_it_as_a_course(self, baked) -> None:
        """Through the game's own reader, so the format is not just asserted
        to be right here and different over there."""
        courses = pytest.importorskip('glisteel.world')
        _project, result, _document = baked
        found = courses.load_courses(result.tileset)
        assert found and found[0].closed
        assert found[0].length > 1000.0


class TestTheGroundUnderIt:
    def test_the_drawn_route_reshaped_the_land(self, baked) -> None:
        """The earthworks are in the baked ground, not only in the preview."""
        project, _result, _document = baked
        from OpenGLContext.loaders.tiles3d.procedural import terrain_height
        world = project.world()
        conformed = world.height_fn()
        x, z = project.routes[0].points[0]
        on_road = float(np.asarray(conformed(np.array([x]), np.array([z])))[0])
        natural = float(np.asarray(terrain_height(np.array([x]),
                                                  np.array([z])))[0])
        assert on_road != pytest.approx(natural, abs=1e-6)


def _uris(entry, out=None):
    out = [] if out is None else out
    content = entry.get('content')
    if content and content.get('uri'):
        out.append(content['uri'])
    for child in entry.get('children', ()):
        _uris(child, out)
    return out


class TestWhereTheLapBegins:
    """The start/finish is a designer's decision, and the game reads it back."""

    def test_the_road_the_game_reads_says_where_a_lap_starts(self, baked) -> None:
        _project, _result, document = baked
        road = document['extras']['roads'][0]
        assert 'start' in road
        assert 0.0 <= road['start'] <= road['length']

    def test_a_chosen_start_travels_into_the_world(self, tmp_path) -> None:
        project = _drawn()
        project.route().start = 5
        _result, document = _bake(project, str(tmp_path / 'world'), depth=1)
        assert document['extras']['roads'][0]['start'] > 0.0

    def test_a_circuit_turned_round_is_a_different_line(self, tmp_path) -> None:
        project = _drawn()
        forward = project.world().circuit().points.copy()
        project.route().reversed = True
        backward = project.world().circuit().points
        assert not np.allclose(forward[:len(backward)], backward[:len(forward)])


@pytest.fixture(scope='module')
def watered(tmp_path_factory):
    """One bake of a track with a river across it, and the project it came
    from -- the same bake answers both questions asked of it below."""
    from OpenGLContext_editor.world.hydrology import Spring
    project = _drawn()
    project.landscape.springs.append(Spring(at=(-380.0, 380.0)))
    result, _document = _bake(project, str(tmp_path_factory.mktemp('rivers')))
    return project, result


class TestTheRiversInIt:
    """A river the editor shows and the baked world does not is a river
    nobody can drive to."""

    def test_a_track_with_a_river_bakes_one(self, watered) -> None:
        project, result = watered
        assert project.landscape.channels(), "no river to bake"
        assert result.tiles > 1

    def test_the_water_is_in_the_tiles(self, watered) -> None:
        """Not merely in the layer list: the baker has to have written it."""
        _project, result = watered
        found = []
        for name in os.listdir(result.directory):
            if name.endswith('.glb'):
                with open(os.path.join(result.directory, name), 'rb') as handle:
                    if b'river' in handle.read():
                        found.append(name)
        assert found, "no tile carries a river"


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
