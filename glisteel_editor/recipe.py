"""What a track is made of, declared once and read from two places.

:class:`~OpenGLContext_editor.world.procedural.ProceduralWorld` takes about
twenty parameters and declares the ones a recipe may set
(``ProceduralWorld.SETTINGS``). :data:`WORLD_SETTINGS` is that table as
``glisteel-bake`` offers it, so a recipe -- a TOML file committed beside the
code -- can name them too.

A recipe is what makes a released track something that can be rebuilt from the
tag that produced it, rather than from a command somebody remembers typing::

    # tracks/tidewater.toml
    name = "Tidewater"
    seed = 23
    water_level = 20.0      # the valleys flood; the circuit runs on causeways
    maximum_bank = 0.02     # flat corners, so the causeways read as causeways

Validation is strict: a key no setting is called is refused rather than ignored,
because the alternative is a track baked wrong with nothing saying so.

Three of the world's parameters are deliberately not here, each needing a file
or an object rather than a number: ``route`` (a drawn centreline), ``channels``
(river beds) and ``source`` (a height source such as a real DEM).
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ['BAKE_SETTINGS', 'BadRecipe', 'Setting', 'Settings',
           'WORLD_SETTINGS', 'add_settings', 'read_recipe', 'resolve',
           'world_for']


class BadRecipe(ValueError):
    """The recipe could not be read, or something in it is not a setting.

    Raised rather than ignoring the line: a misspelled key that was skipped is a
    track baked to settings nobody chose, and nothing would say so.
    """


@dataclass(frozen=True)
class Setting:
    """One thing a recipe or a command line may name.

    ``kind`` is what the value has to be; ``choices`` bounds it where only some
    values mean anything. ``switch`` is the command-line spelling where it is
    not simply the name with dashes -- a flag that turns something *off* reads
    better as ``--no-structures`` than as ``--structures false``.
    """

    name: str
    kind: Callable[[Any], Any]
    help: str
    choices: tuple[Any, ...] | None = None
    switch: str | None = None
    #: For a boolean: the flag turns the setting to this.
    flag_to: bool | None = None

    @property
    def option(self) -> str:
        return self.switch or '--%s' % (self.name.replace('_', '-'),)

    def read(self, value: Any) -> Any:
        """``value`` as this setting, or say why it is not one."""
        if self.kind is bool:
            if not isinstance(value, bool):
                raise BadRecipe('%s is %r, and it is true or false'
                                % (self.name, value))
            return value
        try:
            if self.kind in (int, float) and isinstance(value, bool):
                raise TypeError('a boolean is not a number')
            if self.kind is int and isinstance(value, float) \
                    and not value.is_integer():
                raise ValueError('a fraction is not a whole number')
            made = self.kind(value)
        except (TypeError, ValueError) as error:
            raise BadRecipe('%s is %r, which is not %s'
                            % (self.name, value, self.kind.__name__)) from error
        if self.choices is not None and made not in self.choices:
            raise BadRecipe('%s is %r, and it is one of %s'
                            % (self.name, made,
                               ', '.join(repr(one) for one in self.choices)))
        return made


#: How a boolean setting is spelled on the command line, where the flag turns
#: it off. The rest are ``--no-<name>``.
_SWITCHES = {'closed': '--open'}


def _offered(declared: Any) -> Setting:
    """One of the world's own settings as a recipe and a command line take it."""
    if declared.kind is not bool:
        return Setting(declared.name, declared.kind, declared.help,
                       choices=declared.choices)
    switch = _SWITCHES.get(declared.name,
                           '--no-%s' % (declared.name.replace('_', '-'),))
    return Setting(declared.name, bool, declared.help, switch=switch,
                   flag_to=False)


def _world_settings() -> tuple[Setting, ...]:
    """What the world is: everything that changes the place being driven
    through, as :class:`ProceduralWorld` declares it
    (:attr:`~OpenGLContext_editor.world.procedural.ProceduralWorld.SETTINGS`)."""
    from OpenGLContext_editor.world.procedural import ProceduralWorld
    return tuple(_offered(one) for one in ProceduralWorld.SETTINGS)


#: What the world is: everything that changes the place being driven through.
WORLD_SETTINGS: tuple[Setting, ...] = _world_settings()

#: What the *bake* is: how the world is cut up, not what it is.
BAKE_SETTINGS: tuple[Setting, ...] = (
    Setting('depth', int, 'how many times the tree subdivides; each level is '
            'four times the tiles and twice the ground detail'),
    Setting('max_instances', int,
            'cap on instances written into any one tile'),
)

_BY_NAME = {one.name: one for one in WORLD_SETTINGS + BAKE_SETTINGS}


@dataclass
class Settings:
    """What one bake was told, after the recipe and the command line agree.

    ``world`` holds only what was actually named. A setting nobody gave is
    absent rather than repeated here at the world's own default, so the default
    stays in one place -- the world -- and changing it there changes it here.
    """

    name: str | None = None
    world: dict[str, Any] = field(default_factory=dict)
    depth: int = 4
    max_instances: int | None = None


def add_settings(parser: argparse.ArgumentParser) -> None:
    """Give ``parser`` an option for every setting.

    Defaults are ``None`` throughout, so "not given" is distinguishable from
    "given the same value the world would have chosen" -- which is what lets the
    command line outrank a recipe without restating every default.
    """
    for one in WORLD_SETTINGS + BAKE_SETTINGS:
        if one.kind is bool:
            parser.add_argument(one.option, dest=one.name, default=None,
                                action='store_const', const=one.flag_to,
                                help=one.help)
        else:
            parser.add_argument(one.option, dest=one.name, type=one.kind,
                                default=None, choices=one.choices,
                                help=one.help)


def read_recipe(path: str) -> dict[str, Any]:
    """The settings a recipe file names, checked but not yet applied."""
    document = _read_toml(path)
    named: dict[str, Any] = {}
    for key, value in document.items():
        if key == 'name':
            named['name'] = str(value)
            continue
        setting = _BY_NAME.get(key)
        if setting is None:
            raise BadRecipe(
                '%s: %r is not a setting. It is one of: name, %s'
                % (path, key, ', '.join(sorted(_BY_NAME))))
        try:
            named[key] = setting.read(value)
        except BadRecipe as error:
            raise BadRecipe('%s: %s' % (path, error)) from error
    return named


def resolve(options: Any) -> Settings:
    """What the recipe and the command line together say this bake is.

    The command line outranks the recipe, so one recipe bakes at a draft depth
    or another seed without being edited.
    """
    named = read_recipe(options.recipe) if getattr(options, 'recipe', None) \
        else {}
    for one in WORLD_SETTINGS + BAKE_SETTINGS:
        given = getattr(options, one.name, None)
        if given is not None:
            named[one.name] = one.read(given)
    if getattr(options, 'name', None):
        named['name'] = options.name

    made = Settings(name=named.pop('name', None))
    for one in BAKE_SETTINGS:
        if one.name in named:
            setattr(made, one.name, named.pop(one.name))
    made.world = named
    return made


def world_for(settings: Settings) -> Any:
    """The world these settings describe.

    The tree's ``depth`` is a bake setting and the world is told it as well: a
    tiled world's ground is only as fine as its deepest tile, and what a portal
    has to cover is measured against a cell of it.
    """
    from OpenGLContext_editor.world.procedural import ProceduralWorld
    return ProceduralWorld(depth=settings.depth, **settings.world)


def _read_toml(path: str) -> dict[str, Any]:
    """A TOML document, whatever reads one on this interpreter.

    ``tomllib`` is the standard library's from 3.11; ``tomli`` is the same
    reader under its earlier name, and a declared dependency below that.
    """
    try:
        import tomllib as toml
    except ImportError:                     # pragma: no cover - Python 3.10
        try:
            import tomli as toml  # type: ignore[no-redef]
        except ImportError as error:       # pragma: no cover - not installed
            raise BadRecipe(
                'reading a recipe needs tomli on Python 3.10; it is a declared '
                'dependency, so this is an incomplete install') from error
    if not os.path.isfile(path):
        raise BadRecipe('there is no recipe at %s' % (path,))
    try:
        with open(path, 'rb') as handle:
            return toml.load(handle)
    except (OSError, ValueError) as error:
        raise BadRecipe('cannot read the recipe %s: %s' % (path, error)) \
            from error
