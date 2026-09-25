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
import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from typing import Any

from OpenGLContext import atomicfiles
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

__all__ = ['ArtDiffers', 'BadRecipe', 'SHARED_ART', 'Settings', 'build_parser',
           'describe', 'main', 'read_recipe', 'resolve', 'split_art',
           'world_for']

#: What a bake writes that says nothing about which circuit is being driven, and
#: so is the same in every track baked from the same art. Measured across the
#: four launch tracks: byte-identical in all of them. ``signs/`` is deliberately
#: not here -- the signs carry each circuit's own posted limits.
SHARED_ART = ('trees', 'gantry')

#: Where a bake goes when the command line does not say.
DEFAULT_OUTPUT = os.path.join('.', 'baked-world')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='glisteel-bake', description=__doc__.split('\n\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT,
                        help='directory to write the tileset and its tiles into '
                             '(default: %(default)s)')
    parser.add_argument('--art-pack', default=None, metavar='DIR',
                        help='move the art every track shares (%s) into this '
                             'directory instead of leaving it in the track, so '
                             'a release carries one copy rather than one per '
                             'track. Both unpack into the same place, so no '
                             'path changes.' % (', '.join(SHARED_ART),))
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
    parser.add_argument('--no-probes', action='store_true',
                        help="leave each place's environment to be captured "
                             'while the game runs, rather than baking it '
                             '(which needs a GPU the bake can render with)')
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
    if settings.world.get('places', True) and not options.no_probes:
        # Each place's environment is captured now, while the whole world and
        # its art are here to be drawn, so a run uploads it rather than
        # drawing it. Before the art moves: the captures draw the trees.
        from OpenGLContext_editor.bake.probes import bake_probes
        baked = bake_probes(options.output)
        if not options.quiet:
            print('  places:      %d environments baked' % (baked,))
    if options.art_pack:
        moved = split_art(options.output, options.art_pack)
        if not options.quiet:
            print('  shared art: %s' % (', '.join(moved) if moved
                                        else 'already in %s' % options.art_pack))
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


class ArtDiffers(ValueError):
    """A track's shared art is not the art already in the pack.

    The split rests on the art being the same art. Keeping the first copy
    silently would put one track's art under another track's tiles the day that
    stopped being true, and nothing would say so.
    """


def split_art(track: str, pack: str) -> list[str]:
    """Move what ``track`` shares with every other track into ``pack``.

    Returns the directory names moved, which is empty for a bake that wrote no
    shared art (``--forest tiles`` grows the trees into the tiles) and for a
    second track whose art is already in the pack.

    Nothing about a path changes: a track pack and its art pack unpack into the
    same directory, so ``trees/...`` in a tile resolves exactly as it does in a
    bake that never split.
    """
    moved = []
    for name in SHARED_ART:
        here = os.path.join(track, name)
        if not os.path.isdir(here):
            continue
        there = os.path.join(pack, name)
        if os.path.isdir(there):
            if not _same_tree(here, there):
                raise ArtDiffers(
                    "%s is not the %s already in %s. The art packs share is "
                    "meant to be one set of files; two that differ would put "
                    "one track's art under another's tiles."
                    % (here, name, pack))
            atomicfiles.remove_directory(here)
            continue
        # Copied into a staged directory rather than renamed, since the pack
        # may be on another filesystem: an interrupted split leaves the pack
        # without this directory, never with part of it.
        with atomicfiles.staged_directory(there) as staging:
            shutil.copytree(here, staging, dirs_exist_ok=True)
        atomicfiles.remove_directory(here)
        moved.append(name)
    return moved


def _same_tree(one: str, two: str) -> bool:
    """Whether two directories hold the same files with the same bytes."""
    named = {}
    for where in (one, two):
        found = {}
        for root, _, files in os.walk(where):
            for name in files:
                path = os.path.join(root, name)
                with open(path, 'rb') as handle:
                    found[os.path.relpath(path, where)] = hashlib.sha256(
                        handle.read()).hexdigest()
        named[where] = found
    return named[one] == named[two]


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
        closed=bool(world.closed), baked=bake_date())


def bake_date() -> str:
    """The day a bake records, as ISO ``YYYY-MM-DD``.

    ``SOURCE_DATE_EPOCH`` (seconds since 1970, UTC) where it is set, so a
    release rebuilt from its tag on another day is the same bytes; today
    otherwise.
    """
    given = os.environ.get('SOURCE_DATE_EPOCH', '').strip()  # noqa: TID251 the reproducible-builds date, read when a bake records it
    if given.isdigit():
        return datetime.fromtimestamp(int(given), tz=timezone.utc).date().isoformat()
    return date.today().isoformat()



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
