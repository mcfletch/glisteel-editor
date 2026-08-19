"""Putting water on the map: where it wells up, and taking it back.

:class:`WaterEditor` is the landscape's springs being edited; :class:`WaterTool`
is that as a :class:`~OpenGLContext.edit.tools.ToolMode`. Neither knows where
water *goes* -- that is
:mod:`OpenGLContext_editor.world.hydrology`, and the landscape works it out
from the springs and the ground. So a spring is the whole of what a designer
puts down, and the river is what the land does with it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from OpenGLContext.edit.tools import Pointer, ToolMode
from OpenGLContext_editor.world.hydrology import Spring

from glisteel_editor.project import Landscape

__all__ = ['WaterEditor', 'WaterTool']

#: How near the pointer has to be to take hold of a spring, in metres. Scaled
#: by whoever owns the editor so it stays a comfortable number of pixels.
DEFAULT_REACH = 25.0


def _flat(point: Any) -> tuple[float, float]:
    values = np.asarray(point, dtype='d').ravel()
    return (float(values[0]), float(values[-1]))


class WaterEditor:
    """A landscape's springs, and what they were before the last change."""

    HISTORY = 64

    def __init__(self, landscape: Landscape, reach: float = DEFAULT_REACH,
                 on_change: Callable[[], None] | None = None) -> None:
        self.landscape = landscape
        #: How near the pointer must be to take hold of a spring, in metres.
        self.reach = float(reach)
        self.on_change = on_change
        self._past: list[list[Spring]] = []
        self._future: list[list[Spring]] = []
        #: Depth of the gesture in progress: changes inside one are one step.
        self._grouped = 0
        #: Depth of the gesture in progress: changes inside one are one step.
        self._grouped = 0

    @property
    def springs(self) -> list[Spring]:
        return self.landscape.springs

    # -- what is under the pointer ----------------------------------------
    def spring_at(self, where: Any) -> int | None:
        """The index of the spring under a world position, or None."""
        if not self.springs:
            return None
        point = _flat(where)
        distances = [float(np.hypot(spring.at[0] - point[0],
                                    spring.at[1] - point[1]))
                     for spring in self.springs]
        nearest = int(np.argmin(distances))
        return nearest if distances[nearest] <= self.reach else None

    # -- changing it -------------------------------------------------------
    def add(self, where: Any) -> int:
        """Put a spring down."""
        self._take()
        self.springs.append(Spring(at=_flat(where)))
        self._changed()
        return len(self.springs) - 1

    def move(self, index: int, where: Any) -> None:
        """Put a spring somewhere else."""
        if not 0 <= int(index) < len(self.springs):
            return
        self._take()
        self.springs[int(index)] = Spring(at=_flat(where))
        self._changed()

    def remove(self, index: int) -> None:
        """Take a spring away, and the river with it."""
        if not 0 <= int(index) < len(self.springs):
            return
        self._take()
        del self.springs[int(index)]
        self._changed()

    def _take(self) -> None:
        """Keep the springs as they are, unless a gesture already has."""
        if not self._grouped:
            self._remember()

    # -- taking it back ----------------------------------------------------
    def begin_step(self) -> None:
        """Start a gesture: everything until :meth:`end_step` is one change.

        A spring dragged across the map moves a hundred times, and taking that
        back a hundred times is not undo.
        """
        if not self._grouped:
            self._remember()
        self._grouped += 1

    def end_step(self) -> None:
        """Finish the gesture begun by :meth:`begin_step`."""
        self._grouped = max(0, self._grouped - 1)

    def undo(self) -> bool:
        if not self._past:
            return False
        self._future.append(list(self.springs))
        self._restore(self._past.pop())
        return True

    def redo(self) -> bool:
        if not self._future:
            return False
        self._past.append(list(self.springs))
        self._restore(self._future.pop())
        return True

    def _remember(self) -> None:
        self._past.append(list(self.springs))
        del self._past[:-self.HISTORY]
        self._future.clear()

    def _restore(self, state: list[Spring]) -> None:
        self.springs[:] = state
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


class WaterTool(ToolMode):
    """Putting water on the land and watching where it goes.

    * **Left click** puts a spring down; the river runs from it when the
      pointer is let go.
    * **Drag** a spring to move it, and the river with it.
    * **Right click** a spring to take it away. The right button over open
      ground is left alone, so it still moves the map.
    """

    def __init__(self, editor: WaterEditor, **named: Any) -> None:
        named.setdefault('name', 'water')
        named.setdefault('label', 'Place water')
        super().__init__(**named)
        self.editor = editor
        self._dragging: int | None = None

    def cancel(self) -> None:
        """Put a dragged spring back where it started.

        Placing one and dragging it is a single gesture, so abandoning it takes
        the spring away again rather than leaving it where the pointer went.
        """
        if self._dragging is not None:
            self.editor.end_step()
            self.editor.undo()
        self._dragging = None

    def on_press(self, pointer: Pointer) -> bool:
        if not pointer.on_surface:
            return False
        found = self.editor.spring_at(pointer.world)
        if pointer.button == 2:
            if found is None:
                return False
            self.editor.remove(found)
            return True
        if pointer.button:
            return False
        # One step for the whole gesture, however many pixels it crosses --
        # opened before the spring is placed, so putting one down and dragging
        # it into place is the single change a designer made.
        self.editor.begin_step()
        self._dragging = (found if found is not None
                          else self.editor.add(pointer.world))
        return True

    def on_drag(self, pointer: Pointer) -> bool:
        if self._dragging is None or not pointer.on_surface:
            return False
        self.editor.move(self._dragging, pointer.world)
        return True

    def on_release(self, pointer: Pointer) -> bool:
        taken = self._dragging is not None
        if taken:
            self.editor.end_step()
        self._dragging = None
        return taken

    # -- taking it back -----------------------------------------------------
    def undo(self) -> bool:
        return bool(self.editor.undo())

    def redo(self) -> bool:
        return bool(self.editor.redo())
