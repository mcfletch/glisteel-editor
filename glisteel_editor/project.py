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

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

__all__ = ['Landscape', 'Route', 'Project']

#: What an unsaved project is called until it has a file of its own.
UNTITLED = 'Untitled'


@dataclass
class Landscape:
    """Which landscape the track is cut into.

    The shipped procedural terrain, at a size and a seed. ``resolution`` is the
    ground samples a tile is meshed at and ``tree_density`` is trees per square
    metre -- the two knobs that decide what a baked world costs to draw.
    """

    extent: float = 2048.0
    seed: int = 11
    resolution: int = 33
    tree_density: float = 0.004

    def to_json(self) -> dict[str, Any]:
        return {'extent': self.extent, 'seed': self.seed,
                'resolution': self.resolution, 'treeDensity': self.tree_density}

    @classmethod
    def from_json(cls, document: dict[str, Any]) -> Landscape:
        return cls(extent=float(document.get('extent', 2048.0)),
                   seed=int(document.get('seed', 11)),
                   resolution=int(document.get('resolution', 33)),
                   tree_density=float(document.get('treeDensity', 0.004)))


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

    def plan(self) -> np.ndarray:
        """The points as an ``(N,2)`` array, for the road generator."""
        if not self.points:
            return np.zeros((0, 2), dtype='d')
        return np.asarray(self.points, dtype='d').reshape(-1, 2)

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
                'points': [[float(x), float(z)] for x, z in self.points]}

    @classmethod
    def from_json(cls, document: dict[str, Any]) -> Route:
        return cls(name=str(document.get('name', 'road')),
                   closed=bool(document.get('closed', True)),
                   points=[(float(p[0]), float(p[1]))
                           for p in document.get('points', ())])


@dataclass
class Project:
    """One track: the landscape, the routes drawn on it, and the file."""

    #: Bumped when the file's shape changes. A file from a *later* version is
    #: refused rather than half-read: silently dropping what this version does
    #: not understand loses a designer's work without saying so.
    VERSION = 1

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
            road=drivable,
            route=route.plan() if (drivable and route is not None) else None,
            closed=bool(route.closed) if route is not None else True,
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
        """Write the project out, and remember where it went."""
        target = path or self.path
        if not target:
            raise ValueError("a project with no file must be told where to go")
        with open(target, 'w') as handle:
            json.dump(self.to_json(), handle, indent=2, sort_keys=False)
            handle.write('\n')
        self.path = target
        self.dirty = False
        return target

    @classmethod
    def open(cls, path: str) -> Project:
        """Read a project back."""
        with open(path) as handle:
            project = cls.from_json(json.load(handle))
        project.path = path
        project.dirty = False
        return project

    def copy(self, **changes: Any) -> Project:
        """This project with something different about it."""
        return replace(self, **changes)


def new_project(name: str = UNTITLED, extent: float = 2048.0,
                seed: int = 11, points: Sequence[tuple[float, float]] = ()
                ) -> Project:
    """An empty track on a fresh landscape, ready to draw on."""
    return Project(name=name, landscape=Landscape(extent=extent, seed=seed),
                   routes=[Route(name='circuit', points=list(points))])
