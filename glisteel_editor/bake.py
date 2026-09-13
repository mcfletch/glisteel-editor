"""``glisteel-bake`` -- bake a circuit world into a streamable 3D Tiles dataset.

With no arguments it bakes the shipped circuit world
(:mod:`OpenGLContext_editor.world.procedural`) into a directory and prints where
it put it::

    glisteel-bake --output /tmp/world
    glisteel /tmp/world/tileset.json

``--view`` opens the result in ``oglc-view`` instead of driving it. Everything
else on the command line tunes the world's size, its tile detail, and how deep
the tree refines.

The world is a *racing circuit* in hill country -- an oval bent out of round,
held to a design speed, carried over the low ground and bored through the high
-- which is why the command belongs to the game's tools rather than to the
engine's.  The baker under it (:func:`OpenGLContext_editor.bake.driver.bake_world`)
takes any layers at all.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from OpenGLContext_editor.bake.driver import bake_summary, bake_world
from OpenGLContext_editor.bake.manifest import (
    WorldManifest,
    carried,
    world_name,
    write_manifest,
)
from OpenGLContext_editor.world.procedural import ProceduralWorld

from .recipe import (
    BadRecipe,
    Settings,
    add_settings,
    read_recipe,
    resolve,
    world_for,
)

__all__ = ['BadRecipe', 'Settings', 'build_parser', 'describe', 'main',
           'read_recipe', 'resolve', 'world_for']

#: Where a bake goes when the command line does not say.
DEFAULT_OUTPUT = os.path.join('.', 'baked-world')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='glisteel-bake', description=__doc__.split('\n\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT,
                        help='directory to write the tileset and its tiles into '
                             '(default: %(default)s)')
    parser.add_argument('--recipe', default=None, metavar='FILE',
                        help='a track written down: a TOML file naming any of '
                             'the settings below. What is also given on the '
                             'command line outranks it.')
    parser.add_argument('--name', default=None,
                        help='what this world is called, for anything offering '
                             'a choice of them (default: the output '
                             "directory's own name)")
    add_settings(parser)
    parser.add_argument('--force', action='store_true',
                        help='overwrite the output directory if it already holds '
                             'a baked world')
    parser.add_argument('--view', action='store_true',
                        help='open the baked world in oglc-view when it is done')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='say nothing but the tileset path')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    try:
        settings = resolve(options)
    except BadRecipe as error:
        print('glisteel-bake: %s' % (error,), file=sys.stderr)
        return 2
    _prepare_output(options.output, force=options.force)

    world = world_for(settings)

    progress = None if options.quiet else _printing_progress()
    # No `bounds`: the region to partition is whatever the layers cover, height
    # included. The world's own `bounds()` is a footprint, and a region with no
    # vertical extent would prune every cell the ground does not pass exactly
    # through.
    result = bake_world(world.layers(), options.output, depth=settings.depth,
                        credits=world.credits(),
                        max_instances=settings.max_instances,
                        progress=progress)
    manifest = describe(world, options, result, name=settings.name)
    write_manifest(options.output, manifest)
    if options.quiet:
        print(result.tileset)
    else:
        print('\r' + ' ' * 40, end='\r')
        print(bake_summary(result))
        print('  world:       %s' % manifest.summary())
        print('\nDrive it with:\n  glisteel %s' % result.tileset)
    if options.view:
        return _view(result.tileset)
    return 0


def describe(world: ProceduralWorld, options: Any, result: Any,
             name: str | None = None) -> WorldManifest:
    """What this bake produced, as the manifest written beside it.

    Read off the **world** rather than off the command line: a setting nobody
    gave is the world's own, and the manifest is a description of what was
    built. ``closed`` in particular is a fact about the circuit -- a chooser
    shows a point-to-point run differently from a lap -- and taking it from
    anywhere else would let the two disagree.

    The name defaults to the output directory's own, tidied by
    :func:`~OpenGLContext_editor.bake.manifest.world_name`.
    """
    road = world.circuit()
    return WorldManifest(
        name=name or options.name or world_name(options.output),
        tileset=os.path.basename(result.tileset),
        seed=world.seed, extent=float(world.extent),
        road_length=float(road.length), structures=carried(road),
        closed=bool(world.closed), baked=date.today().isoformat())



def _prepare_output(directory: str, force: bool) -> None:
    """Make the output directory, refusing to bake over a world unasked."""
    tileset = os.path.join(directory, 'tileset.json')
    if os.path.exists(tileset) and not force:
        raise SystemExit(
            "%s already holds a baked world; pass --force to replace it" % directory)
    os.makedirs(directory, exist_ok=True)


def _printing_progress() -> Callable[[int, int], None]:
    """A progress callback that keeps to one line."""
    def report(done: int, total: int) -> None:
        sys.stdout.write('\r  baking %d/%d nodes' % (done, total))
        sys.stdout.flush()
    return report


def _view(tileset: str) -> int:
    """Hand the baked world to the engine's viewer."""
    viewer = shutil.which('oglc-view')
    if viewer is None:
        print("oglc-view is not on PATH; install OpenGLContext's scripts to use "
              "--view", file=sys.stderr)
        return 1
    return subprocess.call([viewer, tileset])


if __name__ == '__main__':                       # pragma: no cover - module entry
    raise SystemExit(main())
