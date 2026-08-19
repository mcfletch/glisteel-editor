"""A track project: what a designer's work is, and how it survives being saved.

A project is not the world. The world is baked, is large, and is thrown away
and made again; the project is the handful of decisions that produced it -- the
landscape it was made from and the line drawn across it -- and it is what has
to come back exactly when the file is opened tomorrow.
"""
import json

import numpy as np
import pytest

from glisteel_editor.project import Landscape, Project, Route, new_project


def _route(points=((0.0, 0.0), (100.0, 20.0), (200.0, -40.0))):
    return Route(name='circuit', points=[tuple(p) for p in points])


def _project(**named):
    named.setdefault('name', 'Test Circuit')
    named.setdefault('routes', [_route()])
    return Project(**named)


class TestARoute:
    def test_it_is_a_line_of_points_on_the_map(self) -> None:
        assert len(_route().points) == 3

    def test_it_reports_its_length_on_the_flat(self) -> None:
        route = Route(name='straight', closed=False,
                      points=[(0.0, 0.0), (300.0, 400.0)])
        assert route.length() == pytest.approx(500.0)

    def test_a_closed_route_counts_the_way_home(self) -> None:
        square = Route(name='square', closed=True,
                       points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0),
                               (0.0, 100.0)])
        assert square.length() == pytest.approx(400.0)

    def test_an_open_one_does_not(self) -> None:
        square = Route(name='square', closed=False,
                       points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0),
                               (0.0, 100.0)])
        assert square.length() == pytest.approx(300.0)

    def test_too_few_points_is_no_length(self) -> None:
        assert Route(name='dot', points=[(0.0, 0.0)]).length() == 0.0

    def test_it_gives_its_plan_as_an_array_to_generate_from(self) -> None:
        plan = _route().plan()
        assert plan.shape == (3, 2)
        assert np.allclose(plan[1], (100.0, 20.0))

    def test_a_closed_route_is_not_asked_to_repeat_its_first_point(self) -> None:
        """``follow_terrain`` closes a circuit itself; a repeated point here
        would be a zero-length segment for everything else to trip over."""
        square = Route(name='square', closed=True,
                       points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)])
        assert len(square.plan()) == 3


class TestTheLandscape:
    def test_it_says_how_big_the_world_is(self) -> None:
        assert Landscape(extent=4096.0).extent == 4096.0

    def test_it_carries_the_seed_that_makes_it_reproducible(self) -> None:
        assert Landscape(seed=7).seed == 7

    def test_two_with_the_same_settings_are_the_same_landscape(self) -> None:
        assert Landscape(extent=2048.0, seed=3) == Landscape(extent=2048.0, seed=3)


class TestSavingAndOpening:
    def test_a_project_survives_the_round_trip(self, tmp_path) -> None:
        original = _project()
        path = tmp_path / 'track.glisteel'
        original.save(str(path))
        assert Project.open(str(path)) == original

    def test_every_point_comes_back_where_it_was(self, tmp_path) -> None:
        original = _project()
        path = tmp_path / 'track.glisteel'
        original.save(str(path))
        assert Project.open(str(path)).routes[0].points \
            == original.routes[0].points

    def test_the_landscape_comes_back_too(self, tmp_path) -> None:
        original = _project(landscape=Landscape(extent=4096.0, seed=11,
                                                tree_density=0.002))
        path = tmp_path / 'track.glisteel'
        original.save(str(path))
        assert Project.open(str(path)).landscape == original.landscape

    def test_the_file_is_text_a_person_can_read(self, tmp_path) -> None:
        """A project is a few decisions, and a designer should be able to open
        the file and see them."""
        path = tmp_path / 'track.glisteel'
        _project().save(str(path))
        document = json.loads(path.read_text())
        assert document['name'] == 'Test Circuit'
        assert document['routes'][0]['points'][0] == [0.0, 0.0]

    def test_it_says_what_wrote_it(self, tmp_path) -> None:
        path = tmp_path / 'track.glisteel'
        _project().save(str(path))
        document = json.loads(path.read_text())
        assert 'glisteel-editor' in document['generator']

    def test_a_file_from_a_later_version_is_refused_by_name(self, tmp_path) -> None:
        path = tmp_path / 'track.glisteel'
        _project().save(str(path))
        document = json.loads(path.read_text())
        document['version'] = Project.VERSION + 1
        path.write_text(json.dumps(document))
        with pytest.raises(ValueError, match='newer'):
            Project.open(str(path))

    def test_saving_remembers_where_it_was_saved(self, tmp_path) -> None:
        project = _project()
        path = tmp_path / 'track.glisteel'
        project.save(str(path))
        assert project.path == str(path)

    def test_opening_remembers_where_it_came_from(self, tmp_path) -> None:
        path = tmp_path / 'track.glisteel'
        _project().save(str(path))
        assert Project.open(str(path)).path == str(path)


class TestKnowingItHasChanged:
    def test_a_fresh_project_has_nothing_to_lose(self) -> None:
        assert not _project().dirty

    def test_moving_a_point_makes_it_dirty(self) -> None:
        project = _project()
        project.routes[0].points[1] = (150.0, 20.0)
        project.touch()
        assert project.dirty

    def test_saving_makes_it_clean_again(self, tmp_path) -> None:
        project = _project()
        project.touch()
        project.save(str(tmp_path / 'track.glisteel'))
        assert not project.dirty

    def test_it_has_something_to_call_itself_before_it_is_saved(self) -> None:
        assert _project().title()

    def test_once_saved_it_is_called_after_its_file(self, tmp_path) -> None:
        project = _project()
        project.save(str(tmp_path / 'monaco.glisteel'))
        assert 'monaco' in project.title()

    def test_unsaved_work_shows_in_the_title(self) -> None:
        project = _project()
        project.touch()
        assert project.title().endswith('*')


class TestWhatTheBakerIsGiven:
    def test_the_world_takes_the_landscape_s_settings(self) -> None:
        project = _project(landscape=Landscape(extent=1024.0, seed=5,
                                               tree_density=0.001))
        world = project.world()
        assert world.extent == 1024.0
        assert world.seed == 5
        assert world.tree_density == 0.001

    def test_the_circuit_is_the_route_that_was_drawn(self) -> None:
        project = _project(routes=[Route(
            name='circuit', closed=True,
            points=[(-300.0, -200.0), (300.0, -200.0), (300.0, 200.0),
                    (-300.0, 200.0)])])
        circuit = project.world().circuit()
        assert circuit.length > 1500.0

    def test_a_project_with_no_route_bakes_a_world_without_one(self) -> None:
        assert not _project(routes=[]).world().road

    def test_a_route_of_one_point_is_not_a_road(self) -> None:
        project = _project(routes=[Route(name='dot', points=[(0.0, 0.0)])])
        assert not project.world().road


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


class TestTheHeightSource:
    """The landscape's ground: a base, and the edits a designer made to it."""

    def test_a_fresh_project_is_the_shipped_landscape(self) -> None:
        from OpenGLContext_editor.world.height import ProceduralBase
        project = new_project()
        assert isinstance(project.landscape.source.base, ProceduralBase)
        assert project.landscape.source.edits == []

    def test_the_source_is_written_into_the_file(self, tmp_path) -> None:
        project = new_project()
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        with open(path) as handle:
            document = json.load(handle)
        assert document['landscape']['source']['base']['kind'] == 'procedural'

    def test_it_comes_back_when_the_file_is_opened(self, tmp_path) -> None:
        from OpenGLContext_editor.world.height import ProceduralBase
        project = new_project()
        project.landscape.source.base = ProceduralBase(relief=0.25)
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        assert Project.open(path).landscape.source.base.relief == 0.25

    def test_a_track_written_before_there_was_one_still_opens(self, tmp_path) -> None:
        """A version-1 file has no source block; it reads as the old landscape."""
        from OpenGLContext_editor.world.height import DEFAULT_RELIEF
        path = tmp_path / 'old.glisteel'
        path.write_text(json.dumps({
            'generator': 'glisteel-editor', 'version': 1, 'name': 'Old',
            'landscape': {'extent': 1024.0, 'seed': 3},
            'routes': [{'name': 'circuit', 'closed': True,
                        'points': [[0.0, 0.0], [100.0, 0.0]]}],
        }))
        project = Project.open(str(path))
        assert project.landscape.extent == 1024.0
        assert project.landscape.source.base.relief == DEFAULT_RELIEF

    def test_the_world_is_built_on_the_source(self) -> None:
        import numpy as np
        from OpenGLContext_editor.world.height import ProceduralBase
        project = new_project(extent=512.0)
        project.landscape.source.base = ProceduralBase(relief=0.25)
        ground = project.world().natural()
        point = (np.asarray([10.0]), np.asarray([20.0]))
        from OpenGLContext.loaders.tiles3d.procedural import terrain_height
        assert np.allclose(ground(*point), terrain_height(*point) * 0.25)

    def test_the_file_says_which_version_wrote_it(self) -> None:
        assert Project.VERSION >= 2


class TestStartingFromAPreset:
    def test_a_project_can_be_made_on_a_named_landscape(self) -> None:
        from OpenGLContext_editor.world.presets import PresetBase
        project = new_project(base=PresetBase(name='canyon'))
        assert project.landscape.source.base == PresetBase(name='canyon')

    def test_the_choice_survives_being_saved(self, tmp_path) -> None:
        from OpenGLContext_editor.world.presets import PresetBase
        project = new_project(base=PresetBase(name='mountains', relief=0.6))
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        assert Project.open(path).landscape.source.base \
            == PresetBase(name='mountains', relief=0.6)

    def test_the_world_is_built_on_it(self) -> None:
        import numpy as np
        from OpenGLContext_editor.world.presets import PresetBase
        project = new_project(extent=512.0, base=PresetBase(name='hills'))
        point = (np.asarray([10.0]), np.asarray([20.0]))
        assert np.allclose(project.world().natural()(*point),
                           PresetBase(name='hills').sample(*point))


class TestChoosingTheGroundFromTheCommandLine:
    def _options(self, argv):
        from glisteel_editor.app import build_parser
        return build_parser().parse_args(argv)

    def test_nothing_asked_for_is_the_shipped_landscape(self) -> None:
        from glisteel_editor.app import terrain_base
        assert terrain_base(self._options([])) is None

    def test_a_named_preset(self) -> None:
        from OpenGLContext_editor.world.presets import PresetBase

        from glisteel_editor.app import terrain_base
        assert terrain_base(self._options(['--terrain', 'canyon'])) \
            == PresetBase(name='canyon')

    def test_a_preset_nobody_ships_says_which_there_are(self) -> None:
        from glisteel_editor.app import terrain_base
        with pytest.raises(SystemExit) as raised:
            terrain_base(self._options(['--terrain', 'atlantis']))
        assert 'canyon' in str(raised.value)

    def test_an_elevation_file_with_a_centre(self) -> None:
        from OpenGLContext_editor.world.dem import DEMBase

        from glisteel_editor.app import terrain_base
        base = terrain_base(self._options(
            ['--dem', '/data/N47E008.hgt', '--centre', '47.5,8.5',
             '--datum', '12']))
        assert base == DEMBase(path='/data/N47E008.hgt', centre=(47.5, 8.5),
                               datum=12.0)

    def test_an_elevation_file_with_no_centre_says_so(self) -> None:
        from glisteel_editor.app import terrain_base
        with pytest.raises(SystemExit) as raised:
            terrain_base(self._options(['--dem', '/data/N47E008.hgt']))
        assert '--centre' in str(raised.value)

    def test_an_elevation_file_wins_over_a_preset(self) -> None:
        from OpenGLContext_editor.world.dem import DEMBase

        from glisteel_editor.app import terrain_base
        base = terrain_base(self._options(
            ['--terrain', 'hills', '--dem', '/data/N47E008.hgt',
             '--centre', '0,0']))
        assert isinstance(base, DEMBase)


class TestSurvivingBeingWritten:
    """A project file is the only copy of a designer's decisions.

    Everything else -- the world, the tiles, the road -- is thrown away and made
    again. So the write has to be one that cannot leave the file half-way
    between two versions, and the encoding has to be one that reads the same on
    another machine.
    """

    def test_a_name_outside_ascii_survives_the_round_trip(self, tmp_path) -> None:
        path = str(tmp_path / 'circuit.glisteel')
        _project(name='Nürburgring — Nordschleife').save(path)
        assert Project.open(path).name == 'Nürburgring — Nordschleife'

    def test_it_is_written_as_utf_8_whatever_the_locale_is(self, tmp_path) -> None:
        path = str(tmp_path / 'circuit.glisteel')
        _project(name='Ålesund').save(path)
        # Read as bytes and decoded explicitly: a file written in the platform's
        # own encoding reads as something else, or not at all, elsewhere.
        assert 'Ålesund' in open(path, 'rb').read().decode('utf-8')

    def test_a_failed_write_leaves_the_previous_version_in_place(self, tmp_path) -> None:
        path = str(tmp_path / 'circuit.glisteel')
        _project(name='Before').save(path)
        broken = _project(name='After')
        broken.landscape = _Unwritable()
        with pytest.raises(OSError):
            broken.save(path)
        assert Project.open(path).name == 'Before'

    def test_nothing_is_left_beside_it_when_a_write_fails(self, tmp_path) -> None:
        path = str(tmp_path / 'circuit.glisteel')
        _project(name='Before').save(path)
        broken = _project(name='After')
        broken.landscape = _Unwritable()
        with pytest.raises(OSError):
            broken.save(path)
        assert [one.name for one in tmp_path.iterdir()] == ['circuit.glisteel']


class _Unwritable:
    """A landscape that refuses to be serialised, as a full disk would."""

    def to_json(self):
        raise OSError('no room on the device')


class TestOpeningSomethingThatIsNotAProject:
    """A file that will not read is a message, not a traceback."""

    def test_a_file_that_is_not_json_says_so(self, tmp_path) -> None:
        path = tmp_path / 'circuit.glisteel'
        path.write_text('this is not a project', encoding='utf-8')
        with pytest.raises(ValueError, match='not a glisteel track'):
            Project.open(str(path))

    def test_json_that_is_not_a_project_says_so(self, tmp_path) -> None:
        path = tmp_path / 'circuit.glisteel'
        path.write_text('[1, 2, 3]', encoding='utf-8')
        with pytest.raises(ValueError, match='not a glisteel track'):
            Project.open(str(path))
