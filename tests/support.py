"""What the tests hand the editor: a pointer, a line, and a project to hold it.

Almost every test here is a designer doing something with the pointer to a route
drawn on a landscape, so almost every test needs the same three things made up
for it. They are made up the same way each time, and the way is not what any of
the tests is about.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from OpenGLContext.edit.tools import Pointer

from glisteel_editor.project import Landscape, Project, Route

#: The landscape the tests draw on: two kilometres square, and always the same
#: one, so a height read off it is the same height in every test that reads it.
EXTENT = 2048.0
SEED = 11


def pointer_at(x: float, z: float, button: int = 0,
               modifiers: Sequence[int] = (0, 0, 0)) -> Pointer:
    """The pointer over a point on the ground, as the map view reports one.

    Screen coordinates are zero because nothing downstream of the map view
    reads them: a tool is given where the pointer is *in the world*, which is
    what the view exists to work out.

        >>> pointer_at(100.0, -200.0).world.tolist()
        [100.0, 0.0, -200.0]
    """
    return Pointer(x=0.0, y=0.0, world=np.array([x, 0.0, z], dtype='d'),
                   button=button, modifiers=tuple(modifiers))


def pointer_over_nothing() -> Pointer:
    """The pointer where there is no ground under it -- over the sky.

    A tool is asked about every movement, including the ones over nothing, and
    what it does about them is its own decision rather than a crash.

        >>> pointer_over_nothing().on_surface
        False
    """
    return Pointer(x=0.0, y=0.0, world=None)


def ring_points(radius: float = 260.0, count: int = 24,
                flatten: float = 1.0) -> list[tuple[float, float]]:
    """A closed circuit of plan points, as a designer would have clicked it.

    ``flatten`` squashes it along Z, for a circuit that wants a long side.

        >>> points = ring_points(radius=10.0, count=4)
        >>> [(round(x, 3), round(z, 3)) for x, z in points]
        [(10.0, 0.0), (0.0, 10.0), (-10.0, 0.0), (-0.0, -10.0)]
    """
    angle = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    return [(float(radius * np.cos(a)), float(radius * flatten * np.sin(a)))
            for a in angle]


def route(points: Sequence[Any] = (), closed: bool = True,
          name: str = 'circuit') -> Route:
    """A route through ``points``, each of which may be any pair.

        >>> route([(0.0, 0.0), (100.0, 0.0)], closed=False).points
        [(0.0, 0.0), (100.0, 0.0)]
    """
    return Route(name=name, closed=closed, points=[tuple(p) for p in points])


def project(points: Sequence[Any] = (), closed: bool = True,
            name: str = 'Test', **named: Any) -> Project:
    """A project holding one route on the standard landscape.

    ``named`` reaches :class:`~glisteel_editor.project.Landscape`, so a test
    that wants a coarser or finer one says so and leaves the rest alone.

        >>> project(ring_points(count=8)).routes[0].closed
        True
        >>> project().landscape.extent
        2048.0
    """
    named.setdefault('extent', EXTENT)
    named.setdefault('seed', SEED)
    return Project(name=name, landscape=Landscape(**named),
                   routes=[route(points, closed=closed)])
