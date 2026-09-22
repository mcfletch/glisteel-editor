"""The views the editor draws the landscape through, and the arrangements of them.

A track is drawn on the **map** and judged from an **angle**, and what stands
beside the road -- a bridge deck, a cutting, a sign -- is placed against the
land's *elevations*. So the editor holds four cameras and shows them in one of
four arrangements: the map alone, the angled view alone, the two side by side,
or all four around a centre.

The cameras are shared by every arrangement, so switching shows what was
already being looked at rather than jumping somewhere else.

The map is the editor's own to drive: the tools draw on it, and a drag there
belongs to whatever tool has the pointer. Every other view answers the pointer
through :class:`~OpenGLContext.edit.viewgestures.ViewGestures` -- a drag pans
an elevation and orbits the angled view, and the wheel zooms whichever the
pointer is over.

None of this is a window or GL: it is the cameras, the rectangles they are
drawn in, and which view an event belongs to.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from OpenGLContext.edit.mapview import MapView, MapViewPlatform
from OpenGLContext.edit.orbitview import OrbitView, OrbitViewPlatform
from OpenGLContext.edit.orthoview import OrthoView, OrthoViewPlatform
from OpenGLContext.edit.viewgestures import ViewGestures
from OpenGLContext.views import View, ViewLayout, ViewStyle

__all__ = ['EditorViews', 'LAYOUTS', 'ELEVATION_BACKGROUND']

#: The arrangements a designer can ask for, in the order the View menu offers
#: them: the map alone, the three-quarter view alone, the two side by side,
#: and the map, two elevations and the angled view around a centre.
LAYOUTS = ('map', 'angled', 'split', 'quad')

#: What an elevation clears to. A flat grey rather than the sky: an elevation
#: is read against the horizon line it draws, and a gradient behind it competes
#: with the land.
ELEVATION_BACKGROUND = (0.32, 0.33, 0.35)

#: The least metres an elevation shows from top to bottom, for ground flat
#: enough that its relief is a line.
LEAST_RELIEF = 100.0


class EditorViews:
    """The editor's four cameras, the layouts of them, and where a click lands.

    ``map_view`` and ``orbit`` are the editor's own cameras, so the tools and
    the read-outs go on working on the same map the layout draws.
    ``directions`` names the two elevations, which are
    :class:`~OpenGLContext.edit.orthoview.OrthoView` directions.
    """

    def __init__(self, map_view: MapView, orbit: OrbitView,
                 directions: Sequence[str] = ('front', 'left'),
                 background: Any = ELEVATION_BACKGROUND) -> None:
        if len(directions) != 2:
            raise ValueError('the editor shows two elevations, not %d'
                             % len(directions))
        sky = ViewStyle(background=True)
        flat = ViewStyle(background=background)
        #: The plan the line is drawn on.
        self.map = View(MapViewPlatform(map_view), name='map', style=sky)
        #: The two orthographic elevations, in the order they are placed.
        self.elevations = [
            View(OrthoViewPlatform(OrthoView(direction)), name=direction,
                 style=flat)
            for direction in directions]
        #: The three-quarter view the land is judged from.
        self.angled = View(OrbitViewPlatform(orbit), name='angled', style=sky)
        self._layouts = {
            'map': ViewLayout([self.map]),
            'angled': ViewLayout([self.angled]),
            'split': ViewLayout.split(self.map, self.angled),
            'quad': ViewLayout.quad(self.map, self.elevations[0],
                                    self.elevations[1], self.angled),
        }
        #: Which arrangement is up.
        self.mode = 'map'
        #: The window the views were last placed in, for measuring a view the
        #: arrangement is not showing.
        self.window = (1, 1)
        self.gestures = ViewGestures(self._layouts[self.mode])
        self.show(self.mode)

    # -- the arrangements --------------------------------------------------
    @property
    def layout(self) -> ViewLayout:
        """The layout the context should draw."""
        return self._layouts[self.mode]

    def show(self, name: str) -> ViewLayout:
        """Arrange the views the way ``name`` says, and answer that layout."""
        if name not in self._layouts:
            raise ValueError('the editor has no %r view; the ones it has are %s'
                             % (name, ', '.join(LAYOUTS)))
        self.mode = name
        layout = self._layouts[name]
        layout.arrange(*self.window)
        # The map is where the tools work, so the cameras leave it alone.
        self.gestures.layout = layout
        self.gestures.views = [view for view in layout.views
                               if view is not self.map]
        return layout

    def showing(self, view: View) -> bool:
        """Whether this view is one the current arrangement draws."""
        return any(view is shown and shown.visible for shown in self.layout.views)

    def maximise(self, view: View | None = None) -> None:
        """Give one view the whole window, or give the arrangement back."""
        self.layout.maximise(view)

    # -- placing them ------------------------------------------------------
    def arrange(self, width: int, height: int) -> list[View]:
        """Place the views in a window this size; the ones to draw, in order."""
        self.window = (int(width) or 1, int(height) or 1)
        return self.layout.arrange(*self.window)

    def size(self, view: View) -> tuple[int, int]:
        """A view's own size, or the window's where the arrangement hides it.

        A view that is about to be shown is measured by the window, so framing
        the landscape in it before it is placed puts the landscape somewhere
        sensible rather than in a one-pixel square.
        """
        return view.size if view.visible else self.window

    def map_local(self, x: float, y: float) -> tuple[float, float]:
        """Window pixel ``(x, y)`` in the map view's own pixels."""
        return self.map.local(x, y)

    def map_size(self) -> tuple[int, int]:
        """How many pixels across and down the map is drawn."""
        return self.size(self.map)

    # -- framing -----------------------------------------------------------
    def frame(self, minimum: tuple[float, float], maximum: tuple[float, float],
              relief: tuple[float, float]) -> None:
        """Fit the landscape into every view.

        ``minimum`` and ``maximum`` are the corners of the ground in plan, and
        ``relief`` the lowest and highest it rises to, which is what the
        elevations are fitted to.
        """
        low, high = float(relief[0]), float(relief[1])
        middle = (low + high) / 2.0
        half = max((high - low) / 2.0, LEAST_RELIEF / 2.0)
        box = ((minimum[0], middle - half, minimum[1]),
               (maximum[0], middle + half, maximum[1]))
        self.map.camera.view.frame(minimum, maximum, self.size(self.map))
        for view in self.elevations:
            view.camera.view.frame(box[0], box[1], self.size(view))
        # The whole box rather than the ground plan: a camera standing off far
        # enough for the landscape's width can still have a hilltop behind it.
        self.angled.camera.view.frame_box(box[0], box[1], self.size(self.angled))

    # -- the pointer -------------------------------------------------------
    def view_for(self, event: Any) -> View | None:
        """The view an event belongs to: the context's answer, or the layout's."""
        found = getattr(event, 'view', None)
        if found is None:
            found = self.layout.route(event)
            event.view = found
        return found

    def handle(self, event: Any) -> bool:
        """Move a camera if the event asks one to; True where it was taken.

        An event in the map view is never taken: the map is the editor's, and
        the tools are asked about it first.
        """
        return self.gestures.handle(event)
