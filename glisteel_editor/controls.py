"""Turning what the pointer did into what the map and the tools should do.

The rule is the one every editor has: **the tool in force is asked first, and
what it does not want moves the map**. So a click on a control point drags the
point and a click on open ground -- which the route tool has no use for once a
line exists -- drags the map under it.

Where the pointer *is* comes from the map rather than from the depth buffer.
A plan view knows exactly which square metre is under a pixel; the pick would
answer with whatever height happened to be drawn there, which is a different
question and a slower one.

Separated from the window so it can be driven by a made-up event: the window is
GL and a window, and none of this is either.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from OpenGLContext.edit.orbitview import OrbitView
from OpenGLContext.edit.tools import Pointer, ToolManager

__all__ = ['MapControls', 'OrbitControls']

#: How near the pointer must be to a control point to take hold of it, in
#: pixels. Turned into metres against the map's scale, so it is the same
#: comfortable distance at any zoom.
GRAB_PIXELS = 12.0

#: What a wheel notch does to the scale.
ZOOM_STEP = 1.25

#: How many degrees the three-quarter view turns per pixel dragged. A drag
#: across the window should be most of the way round it, so a designer can look
#: at the other side of a hill without letting go.
ORBIT_PER_PIXEL = 0.4

#: The wheel arrives as a pair of buttons, as it does everywhere in the engine.
WHEEL_UP, WHEEL_DOWN = 4, 3


class MapControls:
    """The pointer, over a map, driving a set of tools."""

    def __init__(self, view: Any, tools: ToolManager,
                 viewport: Callable[[], tuple[int, int]],
                 height_at: Callable[[float, float], float] | None = None,
                 editor: Any = None,
                 on_change: Callable[[], None] | None = None,
                 on_settle: Callable[[], None] | None = None) -> None:
        self.view = view
        self.tools = tools
        #: Where the window's size comes from, asked each time: it changes.
        self.viewport = viewport
        #: The ground under a map position, for tools that want a 3D point.
        self.height_at = height_at or (lambda x, z: 0.0)
        #: The route editor whose reach is kept in step with the zoom.
        self.editor = editor
        #: Called when the map moved, and when a gesture finished.
        self.on_change = on_change
        self.on_settle = on_settle
        self._panning = False
        self._gesturing = False
        self._from = (0.0, 0.0)

    # -- where the pointer is ----------------------------------------------
    def pointer(self, event: Any) -> Pointer:
        """The pointer, on the screen and on the map."""
        x, y = event.getPickPoint()
        world_x, world_z = self.view.world_from_screen(x, y, self.viewport())
        return Pointer(x=float(x), y=float(y),
                       world=np.array([world_x, self.height_at(world_x, world_z),
                                       world_z], dtype='d'),
                       button=int(getattr(event, 'button', 0)),
                       modifiers=tuple(event.getModifiers()))

    def _grab_reach(self) -> None:
        """Keep a handle the same size to grab at whatever the zoom is."""
        if self.editor is not None:
            self.editor.reach = GRAB_PIXELS * self.view.metres_per_pixel(
                self.viewport())

    # -- what an event does ------------------------------------------------
    def button(self, event: Any) -> bool:
        """A button went down or came up. True if the editor used it."""
        button = int(getattr(event, 'button', 0))
        down = bool(getattr(event, 'state', 0))
        if button in (WHEEL_UP, WHEEL_DOWN):
            if down:
                notches = 1 if button == WHEEL_UP else -1
                # The tool in force is asked first, as it is for every other
                # input: a brush is sized with the wheel, and a designer
                # sculpting turns it far more often than they zoom.
                self._grab_reach()
                if not self.tools.wheel(self.pointer(event), notches):
                    self.zoom(ZOOM_STEP if button == WHEEL_DOWN
                              else 1.0 / ZOOM_STEP, event.getPickPoint())
            return True
        self._grab_reach()
        pointer = self.pointer(event)
        if down:
            if self.tools.press(pointer):
                self._gesturing = True
                return True
            # Nothing the tools wanted, so the button moves the map: with the
            # route tool in force that is the right button, since the left one
            # is how a point is put down.
            self._panning = True
            self._from = event.getPickPoint()
            return True
        was_panning, self._panning = self._panning, False
        took = bool(self.tools.release(pointer))
        if self._gesturing:
            # The line has been left where it is going to be. Whatever costs
            # too much to redo per mouse-move can be redone now.
            self._gesturing = False
            if self.on_settle is not None:
                self.on_settle()
            return True
        return took or was_panning

    def moved(self, event: Any) -> bool:
        """The pointer moved. True if the editor used it."""
        if self._panning:
            x, y = event.getPickPoint()
            self.view.pan(x - self._from[0], y - self._from[1], self.viewport())
            self._from = (float(x), float(y))
            self._changed()
            return True
        return bool(self.tools.move(self.pointer(event)))

    def key(self, name: str, modifiers: tuple[int, int, int]) -> bool:
        """A key. True if a tool used it."""
        return bool(self.tools.key(name, modifiers))

    def zoom(self, factor: float, at: Any = None) -> None:
        """Scale the map, holding the world point under ``at`` still."""
        self.view.zoom(factor, at=at, viewport=self.viewport())
        self._changed()

    def frame(self, minimum: Any, maximum: Any) -> None:
        """Put a region on screen."""
        self.view.frame(minimum, maximum, self.viewport())
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


class OrbitControls:
    """The pointer, in the three-quarter view.

    There is nothing to draw on here -- a click is a ray rather than a place --
    so every button orbits and the wheel moves in and out. Separated from the
    window for the same reason :class:`MapControls` is: the window is GL and a
    window, and none of this is either.
    """

    def __init__(self, view: OrbitView,
                 viewport: Callable[[], tuple[int, int]],
                 on_change: Callable[[], None] | None = None) -> None:
        self.view = view
        self.viewport = viewport
        self.on_change = on_change
        self._from: tuple[float, float] | None = None

    def button(self, event: Any) -> bool:
        """A button went down or came up. Always taken: this view is the
        camera's."""
        button = int(getattr(event, 'button', 0))
        down = bool(getattr(event, 'state', 0))
        if button in (WHEEL_UP, WHEEL_DOWN):
            if down:
                self.view.dolly(1.0 / ZOOM_STEP if button == WHEEL_UP
                                else ZOOM_STEP)
                self._changed()
            return True
        self._from = event.getPickPoint() if down else None
        return True

    def moved(self, event: Any) -> bool:
        """The pointer moved. True if the camera moved with it."""
        if self._from is None:
            return False
        x, y = event.getPickPoint()
        # Measured from where the pointer last was rather than from where the
        # drag began: the camera swings under it, and a fixed origin would make
        # the turn accelerate away.
        self.view.orbit((float(x) - self._from[0]) * ORBIT_PER_PIXEL,
                        (float(y) - self._from[1]) * ORBIT_PER_PIXEL)
        self._from = (float(x), float(y))
        self._changed()
        return True

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
