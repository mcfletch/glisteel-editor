"""A track written down, rather than a command somebody remembers typing.

`ProceduralWorld` takes about twenty parameters and the command line passed
six, so the worlds that could be baked were seeds of one idea. A recipe names
the rest, is committed beside the code, and makes a released track something
that can be rebuilt from the tag that produced it.
"""

import datetime

import pytest
from OpenGLContext_editor.world.procedural import ProceduralWorld

from glisteel_editor import bake
from glisteel_editor import recipe as recipes


def recipe(tmp_path, text, name='track.toml'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


def settings(argv):
    """What the world and the bake are told, for these arguments."""
    return bake.resolve(bake.build_parser().parse_args(argv))


class TestTheKnobsThatReachTheWorld:
    """Each was implemented, documented, and unreachable from the command line."""

    @pytest.mark.parametrize('option,field,given,wanted', [
        ('--water-level', 'water_level', '42.5', 42.5),
        ('--relief', 'relief', '2.0', 2.0),
        ('--maximum-bank', 'maximum_bank', '0.15', 0.15),
        ('--variety', 'variety', '0.8', 0.8),
        ('--posted', 'posted', '120', 120),
        ('--tree-height', 'tree_height', '22.5', 22.5),
        ('--field-resolution', 'field_resolution', '257', 257),
        ('--control-size', 'control_size', '1024', 1024),
        ('--extent', 'extent', '2048', 2048.0),
        ('--seed', 'seed', '23', 23),
    ])
    def test_it_reaches_the_world(self, option, field, given, wanted) -> None:
        assert settings([option, given]).world[field] == wanted

    @pytest.mark.parametrize('option,field', [
        ('--no-structures', 'structures'),
        ('--no-road', 'road'),
        ('--no-places', 'places'),
    ])
    def test_a_switch_that_turns_something_off(self, option, field) -> None:
        assert settings([]).world.get(field, True) is not False
        assert settings([option]).world[field] is False

    def test_a_point_to_point_track_is_not_a_loop(self) -> None:
        """A hill climb has a start and a finish rather than a lap."""
        assert settings(['--open']).world['closed'] is False

    def test_every_setting_the_world_declares_is_offered(self) -> None:
        """The world says what it can be told; the recipe offers all of it,
        so a parameter added there needs nothing added here."""
        declared = [one.name for one in ProceduralWorld.SETTINGS]
        assert [one.name for one in recipes.WORLD_SETTINGS] == declared
        for one, source in zip(recipes.WORLD_SETTINGS,
                               ProceduralWorld.SETTINGS, strict=True):
            assert one.help.startswith(source.help)
            assert one.kind is source.kind
            assert one.choices == source.choices

    def test_what_is_not_named_is_left_to_the_world(self) -> None:
        """Absent means the world's own default, not a value repeated here."""
        assert 'water_level' not in settings([]).world
        assert 'relief' not in settings([]).world

    def test_the_bake_keeps_its_own_options(self) -> None:
        made = settings(['--depth', '3', '--max-instances', '500'])
        assert made.depth == 3 and made.max_instances == 500
        assert 'depth' not in made.world, 'depth is the tree, not the world'


class TestARecipeFile:
    def test_it_names_the_same_things_the_options_do(self, tmp_path) -> None:
        path = recipe(tmp_path, '''
name = "Tidewater"
seed = 23
extent = 2048
water_level = 48.0
maximum_bank = 0.02
''')
        made = settings(['--recipe', path])
        assert made.name == 'Tidewater'
        assert made.world['seed'] == 23
        assert made.world['extent'] == 2048
        assert made.world['water_level'] == 48.0

    def test_the_command_line_outranks_it(self, tmp_path) -> None:
        """So one recipe bakes at a draft depth without being edited."""
        path = recipe(tmp_path, 'name = "Tidewater"\nseed = 23\nextent = 4096\n')
        made = settings(['--recipe', path, '--seed', '99'])
        assert made.world['seed'] == 99
        assert made.world['extent'] == 4096

    def test_the_bake_options_come_from_it_too(self, tmp_path) -> None:
        path = recipe(tmp_path, 'name = "X"\ndepth = 5\nforest = "tiles"\n')
        made = settings(['--recipe', path])
        assert made.depth == 5 and made.world['forest'] == 'tiles'

    def test_a_key_no_option_is_called_is_refused(self, tmp_path) -> None:
        """The typo that would otherwise be ignored, and the track baked wrong."""
        path = recipe(tmp_path, 'name = "X"\nwater_lvl = 40.0\n')
        with pytest.raises(bake.BadRecipe) as raised:
            settings(['--recipe', path])
        assert 'water_lvl' in str(raised.value)

    def test_a_file_that_is_not_a_recipe_is_refused(self, tmp_path) -> None:
        path = recipe(tmp_path, 'this is not toml = = =')
        with pytest.raises(bake.BadRecipe):
            settings(['--recipe', path])

    def test_a_file_that_is_not_there_is_refused(self, tmp_path) -> None:
        with pytest.raises(bake.BadRecipe):
            settings(['--recipe', str(tmp_path / 'absent.toml')])

    def test_a_value_of_the_wrong_kind_is_refused(self, tmp_path) -> None:
        path = recipe(tmp_path, 'name = "X"\nseed = "eleven"\n')
        with pytest.raises(bake.BadRecipe) as raised:
            settings(['--recipe', path])
        assert 'seed' in str(raised.value)

    def test_a_fraction_for_a_whole_number_is_refused(self, tmp_path) -> None:
        """Truncated, a depth of 3.7 bakes at 3 and nobody is told."""
        path = recipe(tmp_path, 'name = "X"\ndepth = 3.7\n')
        with pytest.raises(bake.BadRecipe) as raised:
            settings(['--recipe', path])
        assert 'depth' in str(raised.value)

    def test_but_a_whole_number_written_with_a_point_is_one(self, tmp_path
                                                           ) -> None:
        path = recipe(tmp_path, 'name = "X"\nseed = 23.0\n')
        assert settings(['--recipe', path]).world['seed'] == 23

    def test_a_choice_outside_its_choices_is_refused(self, tmp_path) -> None:
        path = recipe(tmp_path, 'name = "X"\nforest = "hedges"\n')
        with pytest.raises(bake.BadRecipe) as raised:
            settings(['--recipe', path])
        assert 'hedges' in str(raised.value)


class TestTheWorldItBuilds:
    """The settings reach a real `ProceduralWorld`, not a dictionary."""

    def test_a_flooded_world_puts_its_water_where_it_was_told(self) -> None:
        world = bake.world_for(settings(['--water-level', '60', '--extent',
                                         '1024']))
        assert world.water_level == 60.0
        assert world.extent == 1024.0

    def test_the_world_knows_how_deep_the_tree_will_go(self) -> None:
        """A tiled world's ground is only as fine as its deepest tile, and
        what is measured against a cell -- a portal's face, the ground cleared
        in front of one -- is measured against that."""
        world = bake.world_for(settings(['--depth', '6', '--extent', '1024']))
        assert world.depth == 6

    def test_an_open_circuit_is_built_open(self) -> None:
        world = bake.world_for(settings(['--open', '--extent', '1024']))
        assert world.closed is False

    def test_the_default_world_is_the_one_it_has_always_been(self) -> None:
        """Nothing here changes what a bake with no arguments produces."""
        made, stock = bake.world_for(settings([])), ProceduralWorld()
        for field in ('extent', 'resolution', 'seed', 'ground', 'forest',
                      'water_level', 'relief', 'maximum_bank', 'variety',
                      'closed', 'structures', 'posted', 'places'):
            assert getattr(made, field) == getattr(stock, field), field


class TestWhatTheManifestSays:
    """A chooser reads it, so it describes the world rather than the command."""

    def made(self, argv, tmp_path):
        class _Result:
            tileset = str(tmp_path / 'tileset.json')
        settings = bake.resolve(bake.build_parser().parse_args(argv))
        world = bake.world_for(settings)
        options = bake.build_parser().parse_args(argv + ['--output',
                                                         str(tmp_path)])
        return bake.describe(world, options, _Result(), name=settings.name)

    def test_a_point_to_point_run_is_not_recorded_as_a_lap(self, tmp_path):
        """It used to say `closed=True` whatever was built."""
        assert self.made(['--open', '--extent', '1024'], tmp_path).closed is False

    def test_a_lap_still_says_so(self, tmp_path):
        assert self.made(['--extent', '1024'], tmp_path).closed is True

    def test_the_seed_and_extent_come_from_the_world(self, tmp_path):
        """They are absent from the command line unless given, so reading them
        from there recorded None."""
        one = self.made(['--extent', '1024'], tmp_path)
        assert one.extent == 1024.0 and one.seed is not None

    def test_the_bake_date_is_the_source_date_where_one_is_given(
            self, tmp_path, monkeypatch):
        """A release rebuilt from its tag on another day is the same bytes."""
        monkeypatch.setenv('SOURCE_DATE_EPOCH', '1700000000')
        assert self.made(['--extent', '1024'], tmp_path).baked == '2023-11-14'

    def test_and_today_where_none_is(self, tmp_path, monkeypatch):
        monkeypatch.delenv('SOURCE_DATE_EPOCH', raising=False)
        assert self.made(['--extent', '1024'], tmp_path).baked == \
            datetime.datetime.now().astimezone().date().isoformat()

    def test_a_recipe_names_the_track(self, tmp_path):
        path = recipe(tmp_path, 'name = "Beacon"\nextent = 1024\n')
        assert self.made(['--recipe', path], tmp_path).name == 'Beacon'
