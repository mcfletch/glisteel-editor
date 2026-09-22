"""The views the editor draws the landscape through, and the arrangements of them.

A track is drawn on the **map** and judged from an **angle**, and what stands
beside the road -- a bridge deck, a cutting, a sign -- is placed against the
land's *elevations*. So the editor holds four cameras and shows them in one of
four arrangements: the map alone, the angled view alone, the two side by side,
or all four around a centre.

The arrangements are the engine's
:class:`~OpenGLContext.multiview.viewset.ViewSet`; what is here is which views
the editor has and how a landscape is fitted into them. The map is the
editor's own to drive -- the tools draw on it, and a drag there belongs to
whatever tool has the pointer -- so it is left out of the views the pointer
moves the cameras of.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from OpenGLContext.edit.mapview import MapView, MapViewPlatform
from OpenGLContext.edit.orbitview import OrbitView, OrbitViewPlatform
from OpenGLContext.multiview import (
    OrthoView,
    OrthoViewPlatform,
    View,
    ViewSet,
    ViewStyle,
)

__all__ = ['editor_views', 'frame_landscape', 'LAYOUTS', 'ELEVATION_BACKGROUND']

#: The arrangements a designer can ask for, in the order the View menu offers
#: them and the order ``v`` takes them in.
LAYOUTS = ('map', 'angled', 'split', 'quad')

#: What an elevation clears to. A flat grey rather than the sky: an elevation
#: is read against the horizon line it draws, and a gradient behind it competes
#: with the land.
ELEVATION_BACKGROUND = (0.32, 0.33, 0.35)

#: The least metres an elevation shows from top to bottom, for ground flat
#: enough that its relief is a line.
LEAST_RELIEF = 100.0


def editor_views(map_view: MapView, orbit: OrbitView,
                 directions: Sequence[str] = ('front', 'left'),
                 background: Any = ELEVATION_BACKGROUND) -> ViewSet:
    """The editor's four views, in the four arrangements it offers.

    ``map_view`` and ``orbit`` are the editor's own cameras, so the tools and
    the read-outs go on working on the same map the layout draws.
    ``directions`` names the two elevations, which are
    :class:`~OpenGLContext.multiview.cameras.OrthoView` directions.
    """
    if len(directions) != 2:
        raise ValueError('the editor shows two elevations, not %d'
                         % len(directions))
    sky = ViewStyle(background=True)
    flat = ViewStyle(background=background)
    views = [View(MapViewPlatform(map_view), name='map', style=sky)]
    views.extend(View(OrthoViewPlatform(OrthoView(direction)), name=direction,
                      style=flat)
                 for direction in directions)
    views.append(View(OrbitViewPlatform(orbit), name='angled', style=sky))
    return ViewSet(
        views,
        arrangements={
            'map': ('map',),
            'angled': ('angled',),
            'split': ('map', 'angled'),
            'quad': ('map', directions[0], directions[1], 'angled'),
        },
        mode='map',
        driven=(directions[0], directions[1], 'angled'))


def frame_landscape(views: ViewSet, minimum: tuple[float, float],
                    maximum: tuple[float, float],
                    relief: tuple[float, float]) -> None:
    """Fit the landscape into every view of ``views``.

    ``minimum`` and ``maximum`` are the corners of the ground in plan, and
    ``relief`` the lowest and highest it rises to, which is what the elevations
    are fitted to. Ground with no relief at all still gets a view with a height
    to it, since an elevation of a line shows nothing.
    """
    low, high = float(relief[0]), float(relief[1])
    middle = (low + high) / 2.0
    half = max((high - low) / 2.0, LEAST_RELIEF / 2.0)
    views.frame((minimum[0], middle - half, minimum[1]),
                (maximum[0], middle + half, maximum[1]))
