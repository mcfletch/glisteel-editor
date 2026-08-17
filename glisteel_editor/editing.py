"""Drawing a route: what the pointer does, and what the line does about it.

:class:`RouteEditor` is the line being edited -- adding a point, moving one,
taking one out, and the two hit tests an editor needs: which point is under the
pointer, and which *segment* is. Both are in metres on the ground rather than
in pixels, so they mean the same thing at any zoom.

:class:`RouteTool` is that as a
:class:`~OpenGLContext.edit.tools.ToolMode`: the gestures a designer uses, and
nothing else. What it does not want -- the right button over open ground, a
click on the sky -- it leaves for the camera.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from OpenGLContext.edit.tools import Pointer, ToolMode

from glisteel_editor.project import Route

__all__ = ['RouteEditor', 'RouteTool']

#: How near the pointer has to be to take hold of something, in metres. Scaled
#: by the map's zoom by whoever owns the editor, so it stays a comfortable
#: number of pixels rather than a fixed distance on the ground.
DEFAULT_REACH = 10.0


def _flat(point: Any) -> tuple[float, float]:
    """A world point as the ``(x, z)`` a route is drawn in."""
    values = np.asarray(point, dtype='d').ravel()
    return (float(values[0]), float(values[-1]))


class RouteEditor:
    """A route being drawn, and what the pointer can reach on it."""

    def __init__(self, route: Route, reach: float = DEFAULT_REACH,
                 on_change: Callable[[], None] | None = None) -> None:
        self.route = route
        #: How near the pointer must be to take hold of a point, in metres.
        self.reach = float(reach)
        #: Called after anything about the line changes.
        self.on_change = on_change
        #: The point the pointer is over, for whoever is drawing the map.
        self.hovered: int | None = None

    # -- what is under the pointer ----------------------------------------
    def point_at(self, where: Any) -> int | None:
        """The index of the point under a world position, or None."""
        plan = self.route.plan()
        if not len(plan):
            return None
        distances = np.linalg.norm(plan - np.asarray(_flat(where)), axis=1)
        nearest = int(distances.argmin())
        return nearest if float(distances[nearest]) <= self.reach else None

    def segment_at(self, where: Any) -> int | None:
        """Where a point put down here would go in the line, or None.

        The answer is an *insertion* index, so a click between points 0 and 1
        gives 1: the new point takes that place and the rest move along.
        """
        plan = self.route.plan()
        if len(plan) < 2:
            return None
        point = np.asarray(_flat(where))
        starts = plan
        ends = np.roll(plan, -1, axis=0)
        if not self.route.closed:
            starts, ends = plan[:-1], plan[1:]
        along = ends - starts
        squared = (along * along).sum(axis=1)
        squared = np.where(squared > 0, squared, 1.0)
        # Where the pointer falls along each segment, clamped to its ends: a
        # click past the end of one belongs to whatever is nearest there.
        fraction = np.clip(((point - starts) * along).sum(axis=1) / squared,
                           0.0, 1.0)
        closest = starts + along * fraction[:, None]
        distances = np.linalg.norm(closest - point, axis=1)
        nearest = int(distances.argmin())
        if float(distances[nearest]) > self.reach:
            return None
        return nearest + 1

    # -- changing it -------------------------------------------------------
    def append(self, where: Any) -> int:
        """Put a point at the end of the line."""
        self.route.points.append(_flat(where))
        self._changed()
        return len(self.route.points) - 1

    def insert(self, index: int, where: Any) -> int:
        """Put a point into the line at ``index``."""
        self.route.points.insert(int(index), _flat(where))
        self._changed()
        return int(index)

    def move(self, index: int, where: Any) -> None:
        """Put the point at ``index`` somewhere else."""
        if not 0 <= int(index) < len(self.route.points):
            return
        self.route.points[int(index)] = _flat(where)
        self._changed()

    def remove(self, index: int) -> None:
        """Take a point out of the line."""
        if not 0 <= int(index) < len(self.route.points):
            return
        del self.route.points[int(index)]
        if self.hovered is not None and self.hovered >= len(self.route.points):
            self.hovered = None
        self._changed()

    def close_route(self, closed: bool) -> None:
        """Say whether the route comes back to where it started."""
        if bool(closed) == bool(self.route.closed):
            return
        self.route.closed = bool(closed)
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


class RouteTool(ToolMode):
    """Drawing and adjusting a route with the pointer.

    * **Click empty ground** and a point goes on the end of the line; click
      *on* the line and it goes in there instead, between the two it fell
      between, because a route is an order and not a set.
    * **Drag a point** to move it. Escape puts it back where it was.
    * **Right-click a point** to take it out. The right button over open ground
      is left alone, so it still orbits.
    * **Delete** takes out whatever the pointer is over.
    """

    def __init__(self, editor: RouteEditor, **named: Any) -> None:
        named.setdefault('name', 'route')
        named.setdefault('label', 'Draw route')
        super().__init__(**named)
        self.editor = editor
        self._dragging: int | None = None
        self._was: tuple[float, float] | None = None

    def leave(self) -> None:
        self.editor.hovered = None

    def cancel(self) -> None:
        """Put a dragged point back where it started."""
        if self._dragging is not None and self._was is not None:
            self.editor.move(self._dragging, self._was)
        self._dragging = None
        self._was = None

    # -- the pointer -------------------------------------------------------
    def on_move(self, pointer: Pointer) -> bool:
        if not pointer.on_surface:
            return False
        found = self.editor.point_at(pointer.world)
        if found == self.editor.hovered:
            return False
        self.editor.hovered = found
        return True

    def on_press(self, pointer: Pointer) -> bool:
        if not pointer.on_surface:
            return False
        found = self.editor.point_at(pointer.world)
        if pointer.button == 2:
            # The right button over a point removes it; over open ground it
            # belongs to the camera.
            if found is None:
                return False
            self.editor.remove(found)
            return True
        if pointer.button:
            return False
        if found is not None:
            self._dragging = found
            self._was = self.editor.route.points[found]
            return True
        segment = self.editor.segment_at(pointer.world)
        if segment is not None:
            self.editor.insert(segment, pointer.world)
        else:
            self.editor.append(pointer.world)
        return True

    def on_drag(self, pointer: Pointer) -> bool:
        if self._dragging is None or not pointer.on_surface:
            return False
        self.editor.move(self._dragging, pointer.world)
        return True

    def on_release(self, pointer: Pointer) -> bool:
        taken = self._dragging is not None
        self._dragging = None
        self._was = None
        return taken

    def on_key(self, name: str, modifiers: tuple[int, int, int]) -> bool:
        if name in ('<delete>', '<backspace>') and self.editor.hovered is not None:
            self.editor.remove(self.editor.hovered)
            return True
        return False
