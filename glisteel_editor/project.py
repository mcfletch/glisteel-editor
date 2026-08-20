"""A track project: a designer's decisions, and the file they live in.

A project is *not* the world. The world is baked, is hundreds of megabytes, and
is thrown away and made again whenever a decision changes. The project is the
handful of decisions that produced it -- which landscape, and what line was
drawn across it -- and it is what has to come back exactly when the file is
opened tomorrow. It is small, it is JSON, and a designer can read it.

Everything that turns those decisions into a world belongs to
:mod:`OpenGLContext_editor`: :meth:`Project.world` hands them over and gets a
world back.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
from OpenGLContext_editor.world.height import HeightSource
from OpenGLContext_editor.world.hydrology import Channel, Spring, channels_for, flow_from

__all__ = ['Landscape', 'Route', 'Project']

#: What an unsaved project is called until it has a file of its own.
UNTITLED = 'Untitled'


@dataclass
class Landscape:
    """Which landscape the track is cut into.

    ``source`` is where the ground comes from: a base -- the shipped procedural
    terrain -- and the ordered stack of edits a designer has made to it. It is
    :class:`~OpenGLContext_editor.world.height.HeightSource`, and it is what
    everything downstream samples.

    ``extent`` is how many metres across the landscape is, ``resolution`` the
    ground samples a tile is meshed at and ``tree_density`` trees per square
    metre -- the two knobs that decide what a baked world costs to draw.
    ``seed`` chooses what stands on the ground: the trees and the rocks.
    """

    extent: float = 2048.0
    seed: int = 11
    resolution: int = 33
    tree_density: float = 0.004
    source: HeightSource = field(default_factory=HeightSource)
    #: Where water wells up. The rivers are *worked out* from these and the
    #: land, so they are not in the file: a bed written down would be the river
    #: as the land used to be, and would stay there when the land moved.
    springs: list[Spring] = field(default_factory=list)
    _rivers: tuple[Any, list[Channel]] | None = field(
        default=None, init=False, repr=False, compare=False)

    # -- the ground it makes ----------------------------------------------
    def ground(self) -> HeightSource:
        """The land with its rivers cut into it.

        The channels come after the edits, so water is routed over the ground
        as the designer left it: raise land upstream and the river finds
        another way down on the next settle, which is what water does.
        """
        channels = self.channels()
        if not channels:
            return self.source
        stacked: list[Any] = list(self.source.edits)
        stacked.extend(channels)
        return HeightSource(base=self.source.base, edits=stacked)

    def channels(self) -> list[Channel]:
        """The beds this landscape's springs cut, worked out once and kept.

        Kept against what they were worked out *from* -- the springs and the
        edit stack -- so a sculpted hill or a moved spring reroutes the water
        and nothing else has to remember to say so.
        """
        signature = self._river_signature()
        if self._rivers is not None and self._rivers[0] == signature:
            return self._rivers[1]
        channels = self._cut_rivers()
        self._rivers = (signature, channels)
        return channels

    def _river_signature(self) -> Any:
        """What the rivers depend on, as something comparable."""
        return (tuple(spring.at for spring in self.springs),
                repr(self.source.to_json()), float(self.extent))

    def _cut_rivers(self) -> list[Channel]:
        if not self.springs:
            return []
        from OpenGLContext.loaders.tiles3d.procedural import WATER_LEVEL
        paths = flow_from(self.source.height_fn(), self.springs,
                          extent=self.extent, water_level=WATER_LEVEL)
        return channels_for(paths)

    # -- the file ----------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return {'extent': self.extent, 'seed': self.seed,
                'resolution': self.resolution, 'treeDensity': self.tree_density,
                'source': self.source.to_json(),
                'springs': [spring.to_json() for spring in self.springs]}

    @classmethod
    def from_json(cls, document: dict[str, Any]) -> Landscape:
        return cls(extent=float(document.get('extent', 2048.0)),
                   seed=int(document.get('seed', 11)),
                   resolution=int(document.get('resolution', 33)),
                   tree_density=float(document.get('treeDensity', 0.004)),
                   source=HeightSource.from_json(document.get('source', {})),
                   springs=[Spring.from_json(entry)
                            for entry in document.get('springs', ())])


@dataclass
class Route:
    """A line drawn on the map: the plan of one road.

    The points are ``(x, z)`` in world metres, in the order they were drawn. No
    heights: a route is a *plan*, and where the road actually runs is what the
    generator works out from the ground under it.

    ``closed`` means it comes back to where it started -- a circuit rather than
    a road from somewhere to somewhere else. The first point is not repeated at
    the end to say so; the generator closes it.
    """

    name: str = 'circuit'
    points: list[tuple[float, float]] = field(default_factory=list)
    closed: bool = True
    #: Which point a lap begins and ends at. The grid stands behind it and the
    #: timing counts from it.
    start: int = 0
    #: Whether the road is driven the other way round from the way it was
    #: drawn. A circuit drawn clockwise and driven anticlockwise is a different
    #: track, not the same one seen from behind.
    reversed: bool = False

    def plan(self) -> np.ndarray:
        """The points as an ``(N,2)`` array, for the road generator.

        In the direction it is driven, so a route turned round is turned round
        here rather than everywhere downstream.

        A **circuit** keeps its first point: a lap begins where it begins, and
        only the direction round the loop changes, so the rest run the other
        way. An **open road** does not have that constraint -- turning one round
        means starting at the far end and driving back -- so the whole line
        reverses. Keeping its first point first would not be the same road
        driven the other way; it would be a different shape.
        """
        if not self.points:
            return np.zeros((0, 2), dtype='d')
        plan = np.asarray(self.points, dtype='d').reshape(-1, 2)
        if not self.reversed:
            return plan
        if self.closed:
            return np.vstack([plan[:1], plan[1:][::-1]])
        return plan[::-1]

    def start_point(self) -> tuple[float, float] | None:
        """Where on the ground a lap begins, or None for a route with no points.

        A start that has fallen off the end of the line -- the point under it
        was taken out -- reads as the first point: a lap still has to begin
        somewhere, and the alternative is a track a game cannot start.
        """
        if not self.points:
            return None
        index = int(self.start)
        if not 0 <= index < len(self.points):
            index = 0
        return self.points[index]

    def length(self) -> float:
        """How far round it is on the flat, in metres.

        On the flat: the ground has not been consulted yet, so this is the
        length of the line the designer drew rather than of the road that will
        come out of it, which climbs and is therefore longer.
        """
        plan = self.plan()
        if len(plan) < 2:
            return 0.0
        if self.closed:
            plan = np.vstack([plan, plan[:1]])
        return float(np.linalg.norm(np.diff(plan, axis=0), axis=1).sum())

    def is_road(self) -> bool:
        """Whether there is enough of a line here to build a road from."""
        return len(self.points) >= 2

    def to_json(self) -> dict[str, Any]:
        return {'name': self.name, 'closed': self.closed,
                'start': int(self.start), 'reversed': bool(self.reversed),
                'points': [[float(x), float(z)] for x, z in self.points]}

    @classmethod
    def from_json(cls, document: dict[str, Any]) -> Route:
        return cls(name=str(document.get('name', 'road')),
                   closed=bool(document.get('closed', True)),
                   start=int(document.get('start', 0)),
                   reversed=bool(document.get('reversed', False)),
                   points=[(float(p[0]), float(p[1]))
                           for p in document.get('points', ())])


@dataclass
class Project:
    """One track: the landscape, the routes drawn on it, and the file."""

    #: Bumped when the file's shape changes. A file from a *later* version is
    #: refused rather than half-read: silently dropping what this version does
    #: not understand loses a designer's work without saying so. Version 2
    #: added the landscape's height source; a version-1 file has none and reads
    #: as the shipped landscape, which is what it was.
    VERSION = 2

    name: str = UNTITLED
    landscape: Landscape = field(default_factory=Landscape)
    routes: list[Route] = field(default_factory=list)
    #: Where this was last saved or opened, or None for work with no file yet.
    path: str | None = None
    #: Whether there is anything in it that the file has not got.
    dirty: bool = False

    # -- what a designer sees ---------------------------------------------
    def title(self) -> str:
        """What to put in the window's title bar."""
        stem = (os.path.splitext(os.path.basename(self.path))[0]
                if self.path else (self.name or UNTITLED))
        return stem + ('*' if self.dirty else '')

    def touch(self) -> None:
        """Note that something has changed since the last save."""
        self.dirty = True

    def route(self, name: str | None = None) -> Route | None:
        """A route by name, or the first one; None if there are none."""
        for candidate in self.routes:
            if name is None or candidate.name == name:
                return candidate
        return None

    def bounds(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The corners of the landscape, as the map view frames a region."""
        half = self.landscape.extent / 2.0
        return ((-half, -half), (half, half))

    # -- the world it describes -------------------------------------------
    def world(self) -> Any:
        """The world these decisions make, ready to bake or to measure.

        Built fresh each time rather than kept: everything downstream of a
        route -- the alignment, the earthworks, where the trees can stand --
        changes when a point moves, and a world held across an edit would be
        answering about the line as it used to be.
        """
        from OpenGLContext_editor.world.procedural import ProceduralWorld
        route = self.route()
        drivable = route is not None and route.is_road()
        return ProceduralWorld(
            extent=self.landscape.extent,
            resolution=self.landscape.resolution,
            tree_density=self.landscape.tree_density,
            seed=self.landscape.seed,
            source=self.landscape.ground(),
            # The beds are already in the source; these give the water in them
            # a surface, so a driven world has the rivers the map shows.
            channels=self.landscape.channels(),
            road=drivable,
            route=route.plan() if (drivable and route is not None) else None,
            closed=bool(route.closed) if route is not None else True,
            start_at=route.start_point() if drivable and route is not None
            else None,
        )

    # -- the file ----------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return {
            'generator': 'glisteel-editor',
            'version': self.VERSION,
            'name': self.name,
            'landscape': self.landscape.to_json(),
            'routes': [route.to_json() for route in self.routes],
        }

    @classmethod
    def from_json(cls, document: dict[str, Any]) -> Project:
        version = int(document.get('version', 0))
        if version > cls.VERSION:
            raise ValueError(
                "this track was saved by a newer glisteel-editor (file version "
                "%d, this one reads %d)" % (version, cls.VERSION))
        return cls(
            name=str(document.get('name', UNTITLED)),
            landscape=Landscape.from_json(document.get('landscape', {})),
            routes=[Route.from_json(entry) for entry in document.get('routes', ())],
        )

    def save(self, path: str | None = None) -> str:
        """Write the project out, and remember where it went.

        Written beside the target and moved onto it, because a project file is
        the only copy of a designer's decisions: a write that truncated the file
        first would leave nothing at all if the disk filled or the machine went
        down half way through, and what it destroyed is the one thing here that
        cannot be made again. ``os.replace`` is atomic on every platform this
        runs on, so the file is either the old version or the new one.

        In UTF-8, so a track named in any language reads back the same on
        another machine rather than in whatever encoding this one prefers, and
        reads as its own name rather than as escapes.
        """
        target = path or self.path
        if not target:
            raise ValueError("a project with no file must be told where to go")
        # ``ensure_ascii=False`` because the file is meant to be read by a
        # person: a track named outside ASCII is its own name in the file
        # rather than a row of escapes.
        document = json.dumps(self.to_json(), indent=2, sort_keys=False,
                              ensure_ascii=False) + '\n'
        beside = os.path.dirname(os.path.abspath(target))
        handle, temporary = tempfile.mkstemp(dir=beside, suffix='.glisteel-new')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as writing:
                writing.write(document)
            os.replace(temporary, target)
        except BaseException:
            # Nothing half-written left beside the designer's file, whatever
            # went wrong -- including an interrupt.
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
        self.path = target
        self.dirty = False
        return target

    @classmethod
    def open(cls, path: str) -> Project:
        """Read a project back.

        A file that is not one is a :class:`ValueError` naming it, rather than
        whatever the parser happened to raise on the way past: what opens a
        project is a menu item, and a designer who picked the wrong file is owed
        a sentence rather than a traceback.
        """
        try:
            with open(path, encoding='utf-8') as handle:
                document = json.load(handle)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('%s is not a glisteel track: %s'
                             % (path, error)) from error
        if not isinstance(document, dict):
            raise ValueError('%s is not a glisteel track: it holds %s rather '
                             'than a track' % (path, type(document).__name__))
        project = cls.from_json(document)
        project.path = path
        project.dirty = False
        return project

    def copy(self, **changes: Any) -> Project:
        """This project with something different about it."""
        return replace(self, **changes)


def new_project(name: str = UNTITLED, extent: float = 2048.0,
                seed: int = 11, points: Sequence[tuple[float, float]] = (),
                base: Any = None) -> Project:
    """An empty track on a fresh landscape, ready to draw on.

    ``base`` is where the ground comes from -- a named preset, an imported
    elevation dataset -- and defaults to the shipped procedural landscape.
    """
    source = HeightSource() if base is None else HeightSource(base=base)
    return Project(name=name,
                   landscape=Landscape(extent=extent, seed=seed, source=source),
                   routes=[Route(name='circuit', points=list(points))])
