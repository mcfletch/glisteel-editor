"""Drawing a route: what the pointer does, and what the line does about it.

:class:`RouteEditor` is the line being edited -- adding a point, moving one,
taking one out, and the two hit tests an editor needs: which point is under the
pointer, and which *segment* is. Both are in metres on the ground rather than
in pixels, so they mean the same thing at any zoom.

:class:`RouteTool` is that as a
:class:`~OpenGLContext.edit.tools.ToolMode`: the gestures a designer uses, and
nothing else. What it does not want -- the right button over open ground, a
click on the sky -- it leaves for the camera.

:func:`editor_tools` is the set of them the editor offers, in the order the
tool palette draws them.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import numpy as np
from OpenGLContext.edit.maptools import PanTool
from OpenGLContext.edit.mapview import MapView
from OpenGLContext.edit.surface import snap_to_height
from OpenGLContext.edit.tools import Pointer, ToolManager, ToolMode

from glisteel_editor.project import Route

__all__ = ['RouteEditor', 'RouteTool', 'RouteState', 'StartTool',
           'editor_tools']


class RouteState(NamedTuple):
    """A route as it was, for putting back.

    Named rather than a bare tuple: what undo restores is four different things
    about a line, and reading them back out by position is how the third and
    fourth come to be swapped by somebody adding a fifth.
    """

    points: list[tuple[float, float]]
    closed: bool
    start: int
    reversed: bool

#: How near the pointer has to be to take hold of something, in metres. Scaled
#: by the map's zoom by whoever owns the editor, so it stays a comfortable
#: number of pixels rather than a fixed distance on the ground.
DEFAULT_REACH = 10.0

#: How far apart the iso-heights a point snaps to are, in metres, and how far a
#: snap may move a point. A contour a kilometre away is not what the pointer
#: meant, and a snap that drags a point across the map is worse than none.
SNAP_INTERVAL = 25.0
SNAP_REACH = 250.0


def _flat(point: Any) -> tuple[float, float]:
    """A world point as the ``(x, z)`` a route is drawn in."""
    values = np.asarray(point, dtype='d').ravel()
    return (float(values[0]), float(values[-1]))


class RouteEditor:
    """A route being drawn, what the pointer can reach on it, and what it was.

    Every change is taken with the line's previous state kept, so it can be
    given back: an editor that cannot undo loses work, and a designer drawing
    with a pointer makes a wrong point every few minutes. A drag is one step
    rather than one per pixel -- see :meth:`begin_step`.
    """

    #: How many changes are remembered. Enough to get out of a wrong turn;
    #: bounded, because a session lasts hours and a route is a list of points
    #: that would otherwise be kept once per pointer movement.
    HISTORY = 64

    def __init__(self, route: Route, reach: float = DEFAULT_REACH,
                 on_change: Callable[[], None] | None = None,
                 height_fn: Callable[[Any, Any], Any] | None = None,
                 snap: bool = False, snap_interval: float = SNAP_INTERVAL,
                 snap_reach: float = SNAP_REACH) -> None:
        self.route = route
        #: How near the pointer must be to take hold of a point, in metres.
        self.reach = float(reach)
        #: Called after anything about the line changes.
        self.on_change = on_change
        #: The ground a point is snapped against; None turns snapping off
        #: whatever :attr:`snap` says, since there is nothing to snap to.
        self.height_fn = height_fn
        #: Whether a point placed or dragged is pulled onto an iso-height.
        self.snap = bool(snap)
        self.snap_interval = float(snap_interval)
        self.snap_reach = float(snap_reach)
        #: The point the pointer is over, for whoever is drawing the map.
        self.hovered: int | None = None
        self._past: list[RouteState] = []
        self._future: list[RouteState] = []
        #: Depth of the gesture in progress: changes inside one are one step.
        self._grouped = 0

    # -- what is under the pointer ----------------------------------------
    def drawn(self) -> np.ndarray:
        """The line as it was drawn, as an ``(N,2)`` array.

        **Not** :meth:`~glisteel_editor.project.Route.plan`, which hands the
        generator the points in the order the road is *driven* and so reverses
        them for a circuit turned round. Everything here answers with an index
        into :attr:`Route.points`, and moves, inserts and removals act on that
        list, so a hit test in plan order would hand back a number meaning a
        different point to every caller that used it.
        """
        return np.asarray(self.route.points, dtype='d').reshape(-1, 2)

    def point_at(self, where: Any) -> int | None:
        """The index of the point under a world position, or None."""
        drawn = self.drawn()
        if not len(drawn):
            return None
        distances = np.linalg.norm(drawn - np.asarray(_flat(where)), axis=1)
        nearest = int(distances.argmin())
        return nearest if float(distances[nearest]) <= self.reach else None

    def segment_at(self, where: Any) -> int | None:
        """Where a point put down here would go in the line, or None.

        The answer is an *insertion* index, so a click between points 0 and 1
        gives 1: the new point takes that place and the rest move along.
        """
        plan = self.drawn()
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

    # -- holding a height --------------------------------------------------
    def snapped(self, where: Any, near: int | None = None,
                snap: bool | None = None) -> tuple[float, float]:
        """A pointer position pulled onto an iso-height, if snapping is on.

        ``near`` is a point of the line whose height to hold; with none, the
        nearest round contour. Holding a *neighbour's* height is the point of
        the thing: a road along a hillside runs at one elevation, and each
        point taking the nearest contour instead would step it up and down the
        slope as the pointer wandered.
        """
        wanted = self.snap if snap is None else bool(snap)
        point = _flat(where)
        if not wanted or self.height_fn is None:
            return point
        held: tuple[float, float] = snap_to_height(
            self.height_fn, point[0], point[1], self._height_of(near),
            interval=self.snap_interval, reach=self.snap_reach)
        return held

    def _height_of(self, index: int | None) -> float | None:
        """The ground under one of the line's points, or None."""
        if index is None or not 0 <= int(index) < len(self.route.points):
            return None
        x, z = self.route.points[int(index)]
        assert self.height_fn is not None
        return float(np.asarray(self.height_fn(np.asarray([x]),
                                               np.asarray([z]))).ravel()[0])

    # -- changing it -------------------------------------------------------
    def append(self, where: Any, snap: bool | None = None) -> int:
        """Put a point at the end of the line."""
        self._take()
        self.route.points.append(
            self.snapped(where, self._last(), snap))
        self._changed()
        return len(self.route.points) - 1

    def insert(self, index: int, where: Any, snap: bool | None = None) -> int:
        """Put a point into the line at ``index``."""
        self._take()
        neighbour = int(index) - 1 if int(index) > 0 else None
        self.route.points.insert(int(index),
                                 self.snapped(where, neighbour, snap))
        self._changed()
        return int(index)

    def move(self, index: int, where: Any, snap: bool | None = None) -> None:
        """Put the point at ``index`` somewhere else."""
        if not 0 <= int(index) < len(self.route.points):
            return
        self._take()
        neighbour = int(index) - 1 if int(index) > 0 else None
        self.route.points[int(index)] = self.snapped(where, neighbour, snap)
        self._changed()

    def _last(self) -> int | None:
        """The point a new one at the end would carry on from."""
        return len(self.route.points) - 1 if self.route.points else None

    def remove(self, index: int) -> None:
        """Take a point out of the line."""
        if not 0 <= int(index) < len(self.route.points):
            return
        self._take()
        del self.route.points[int(index)]
        if self.hovered is not None and self.hovered >= len(self.route.points):
            self.hovered = None
        self._changed()

    def close_route(self, closed: bool) -> None:
        """Say whether the route comes back to where it started."""
        if bool(closed) == bool(self.route.closed):
            return
        self._take()
        self.route.closed = bool(closed)
        self._changed()

    def start_at(self, index: int) -> None:
        """Say which point a lap begins and ends at."""
        if not 0 <= int(index) < len(self.route.points):
            return
        if int(index) == int(self.route.start):
            return
        self._take()
        self.route.start = int(index)
        self._changed()

    def turn_round(self) -> None:
        """Drive the circuit the other way round."""
        self._take()
        self.route.reversed = not self.route.reversed
        self._changed()

    def _take(self) -> None:
        """Keep the line as it is, unless a gesture already has."""
        if not self._grouped:
            self._remember()

    # -- taking it back -----------------------------------------------------
    def begin_step(self) -> None:
        """Start a gesture: everything until :meth:`end_step` is one change.

        A point dragged across the map moves a hundred times, and taking that
        back a hundred times is not undo.
        """
        if not self._grouped:
            self._remember()
        self._grouped += 1

    def end_step(self) -> None:
        """Finish the gesture begun by :meth:`begin_step`."""
        self._grouped = max(0, self._grouped - 1)

    def undo(self) -> bool:
        """Put the line back as it was before the last change. False if there
        was none."""
        if not self._past:
            return False
        self._future.append(self._state())
        self._restore(self._past.pop())
        return True

    def redo(self) -> bool:
        """Do again what was undone. False if nothing was."""
        if not self._future:
            return False
        self._past.append(self._state())
        self._restore(self._future.pop())
        return True

    def _state(self) -> RouteState:
        return RouteState(points=list(self.route.points),
                          closed=bool(self.route.closed),
                          start=int(self.route.start),
                          reversed=bool(self.route.reversed))

    def _restore(self, state: RouteState) -> None:
        self.route.points[:] = state.points
        self.route.closed = state.closed
        self.route.start = state.start
        self.route.reversed = state.reversed
        if self.hovered is not None and self.hovered >= len(self.route.points):
            self.hovered = None
        self._changed()

    def _remember(self) -> None:
        """Keep the line as it is, and forget any future that is now wrong."""
        self._past.append(self._state())
        del self._past[:-self.HISTORY]
        self._future.clear()

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
    * **h** holds the line to a height: a point placed or dragged is pulled
      onto the iso-height its neighbour is on, so a road runs *along* a
      hillside rather than up and down it. **Shift** does the other thing for
      one point, whichever way the mode is set.
    """

    def __init__(self, editor: RouteEditor, **named: Any) -> None:
        named.setdefault('name', 'route')
        named.setdefault('label', 'Draw route')
        super().__init__(**named)
        self.editor = editor
        self._dragging: int | None = None
        self._was: tuple[float, float] | None = None
        self._snapping: bool | None = None

    def leave(self) -> None:
        self.editor.hovered = None

    def cancel(self) -> None:
        """Put a dragged point back where it started."""
        if self._dragging is not None and self._was is not None:
            self.editor.move(self._dragging, self._was)
            self.editor.end_step()
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
        # Shift means the other way from whatever the mode is, so one point on
        # a contour costs no mode change and neither does one off it.
        self._snapping = (not self.editor.snap) if pointer.shifted else None
        if found is not None:
            self._dragging = found
            self._was = self.editor.route.points[found]
            # One step for the whole drag, however many pixels it crosses.
            self.editor.begin_step()
            return True
        segment = self.editor.segment_at(pointer.world)
        if segment is not None:
            self.editor.insert(segment, pointer.world, self._snapping)
        else:
            self.editor.append(pointer.world, self._snapping)
        return True

    def on_drag(self, pointer: Pointer) -> bool:
        if self._dragging is None or not pointer.on_surface:
            return False
        self.editor.move(self._dragging, pointer.world, self._snapping)
        return True

    def on_release(self, pointer: Pointer) -> bool:
        taken = self._dragging is not None
        if taken:
            self.editor.end_step()
        self._dragging = None
        self._was = None
        return taken

    def on_key(self, name: str, modifiers: tuple[int, int, int]) -> bool:
        if name in ('<delete>', '<backspace>') and self.editor.hovered is not None:
            self.editor.remove(self.editor.hovered)
            return True
        if name == 'h':
            self.editor.snap = not self.editor.snap
            return True
        return False

    # -- taking it back -----------------------------------------------------
    def undo(self) -> bool:
        return bool(self.editor.undo())

    def redo(self) -> bool:
        return bool(self.editor.redo())


class StartTool(ToolMode):
    """Saying where a lap begins, and which way round it goes.

    * **Left click** on the line puts the start/finish at the nearest point of
      it. The grid stands behind that point and the timing counts from it.
    * **Right click** turns the circuit round, so it is driven the other way.

    A click that lands nowhere near the line is left alone, so the map still
    moves under it.
    """

    #: How near the pointer has to be to the line to be talking about it, as a
    #: multiple of the editor's reach. Looser than picking a point to drag,
    #: because this is choosing a place on a line rather than a handle.
    REACH = 4.0

    def __init__(self, editor: RouteEditor, **named: Any) -> None:
        named.setdefault('name', 'start')
        named.setdefault('label', 'Start / finish')
        super().__init__(**named)
        self.editor = editor

    def on_press(self, pointer: Pointer) -> bool:
        if not pointer.on_surface or not self.editor.route.points:
            return False
        if pointer.button == 2:
            self.editor.turn_round()
            return True
        if pointer.button:
            return False
        index = self._nearest(pointer.world)
        if index is None:
            return False
        self.editor.start_at(index)
        return True

    def _nearest(self, where: Any) -> int | None:
        """Which point of the line the pointer is nearest, if it is near it.

        Through the editor's own :meth:`RouteEditor.drawn`, so the two hit
        tests over one line cannot come to disagree about which point is which.
        """
        drawn = self.editor.drawn()
        distances = np.linalg.norm(drawn - np.asarray(_flat(where)), axis=1)
        nearest = int(distances.argmin())
        if float(distances[nearest]) > self.editor.reach * self.REACH:
            return None
        return nearest

    # -- taking it back -----------------------------------------------------
    def undo(self) -> bool:
        return bool(self.editor.undo())

    def redo(self) -> bool:
        return bool(self.editor.redo())


def editor_tools(editor: RouteEditor, view: MapView,
                 viewport: Callable[[], tuple[int, int]],
                 on_change: Callable[[], None] | None = None,
                 on_tool: Callable[[Any], None] | None = None,
                 land: Any = None, water: Any = None) -> ToolManager:
    """The tools the editor offers, in the order the palette draws them.

    Drawing comes first because it is what a designer opens the editor to do,
    and it is what the pointer is in until they say otherwise. Moving the map
    is a tool of its own as well as the thing that happens to whatever a tool
    left alone: a designer working close in wants to say "just move the map"
    and have the line stop gaining points where they meant to drag.

    ``land`` is the landscape editor the sculpt tool works on and ``water`` the
    one the water tool works on; with neither, the editor offers only the line
    and the map.
    """
    tools: list[ToolMode] = [RouteTool(editor=editor),
                             StartTool(editor=editor)]
    if land is not None:
        from glisteel_editor.sculpting import SculptTool
        tools.append(SculptTool(editor=land))
    if water is not None:
        from glisteel_editor.water import WaterTool
        tools.append(WaterTool(editor=water))
    tools.append(PanTool(view, viewport, on_change=on_change))
    return ToolManager(tools, on_change=on_tool)
