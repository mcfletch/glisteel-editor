"""Shaping the land with the pointer: the brush, and what it leaves behind.

:class:`LandEditor` is the landscape being edited -- the brush's size and
strength, the strokes made with it, and giving them back. :class:`SculptTool`
is that as a :class:`~OpenGLContext.edit.tools.ToolMode`: press to put a stroke
down, drag to move it, and let go to finish. One gesture is one stroke and one
undo, because a drag across the map is a hundred pointer movements and a
designer who has to press undo a hundred times has lost the gesture, not
undone it.

The stroke itself is
:class:`~OpenGLContext_editor.world.sculpt.SculptStroke`: this holds none of the
arithmetic, only which stroke the designer is making.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from OpenGLContext.edit.tools import Pointer, ToolMode
from OpenGLContext_editor.world.sculpt import SculptStroke

from glisteel_editor.project import Landscape

__all__ = ['LandEditor', 'SculptTool']

#: How wide the brush is to begin with, in metres, and how far one turn of the
#: wheel changes it. A hill a road can be routed around rather than a bump.
DEFAULT_RADIUS = 150.0
RADIUS_STEP = 1.25

#: How many metres a stroke lifts at its centre to begin with, and what one
#: press of the strength keys does to that.
DEFAULT_STRENGTH = 20.0
STRENGTH_STEP = 1.25


class LandEditor:
    """A landscape being sculpted: the brush, the strokes, and what they were.

    Every gesture is kept so it can be given back, because a designer shaping
    ground makes a wrong hill every few minutes and a landscape that cannot be
    put back is a landscape nobody will experiment with.
    """

    #: How many strokes are remembered.
    HISTORY = 64
    #: The narrowest and widest the brush may be, in metres.
    SMALLEST = 10.0
    LARGEST = 2000.0

    def __init__(self, landscape: Landscape, radius: float = DEFAULT_RADIUS,
                 strength: float = DEFAULT_STRENGTH,
                 on_change: Callable[[], None] | None = None) -> None:
        self.landscape = landscape
        #: How wide the brush is, in metres.
        self.radius = float(radius)
        #: How many metres a stroke lifts at its centre.
        self.strength = float(strength)
        #: Called after anything about the land changes.
        self.on_change = on_change
        #: Where the brush is on the ground, or None while the pointer is
        #: somewhere the brush cannot reach. What draws its ring.
        self.at: tuple[float, float] | None = None
        self._past: list[list[Any]] = []
        self._future: list[list[Any]] = []
        #: How many strokes this landscape has had, so each gets its own grain.
        self._made = 0

    # -- the brush ---------------------------------------------------------
    def grow(self, steps: int = 1) -> None:
        """Widen or narrow the brush by wheel notches."""
        self.radius = float(min(max(self.radius * RADIUS_STEP ** int(steps),
                                    self.SMALLEST), self.LARGEST))

    def press_harder(self, steps: int = 1) -> None:
        """Change how many metres a stroke moves the ground."""
        self.strength = float(max(self.strength * STRENGTH_STEP ** int(steps),
                                  0.1))

    # -- the strokes -------------------------------------------------------
    @property
    def edits(self) -> list[Any]:
        """The landscape's edit stack, which is what a stroke goes on."""
        return self.landscape.source.edits

    def begin(self, where: Any, lower: bool = False) -> SculptStroke:
        """Start a stroke, and put it on the landscape at once.

        On the landscape rather than held until the gesture ends, so what the
        designer sees while they are dragging is the ground they are making.
        """
        self._remember()
        self._made += 1
        stroke = self._stroke(where, lower)
        self.edits.append(stroke)
        self._changed()
        return stroke

    def move(self, where: Any, lower: bool = False) -> None:
        """Take the stroke in progress somewhere else."""
        if not self.edits:
            return
        self.edits[-1] = self._stroke(where, lower,
                                      seed=self.edits[-1].seed)
        self._changed()

    def abandon(self) -> None:
        """Drop the stroke in progress, leaving the land as it was."""
        if self._past:
            self._restore(self._past.pop())

    def hover(self, where: Any) -> None:
        """Put the brush under a point on the ground."""
        point = np.asarray(where, dtype='d').ravel()
        self.at = (float(point[0]), float(point[-1]))

    def _stroke(self, where: Any, lower: bool,
                seed: int | None = None) -> SculptStroke:
        self.hover(where)
        point = np.asarray(where, dtype='d').ravel()
        amount = -self.strength if lower else self.strength
        return SculptStroke(centre=(float(point[0]), float(point[-1])),
                            radius=self.radius, amount=float(amount),
                            seed=self._made if seed is None else int(seed))

    # -- taking it back ----------------------------------------------------
    def undo(self) -> bool:
        """Put the land back as it was before the last stroke."""
        if not self._past:
            return False
        self._future.append(list(self.edits))
        self._restore(self._past.pop())
        return True

    def redo(self) -> bool:
        """Make again the stroke that was undone."""
        if not self._future:
            return False
        self._past.append(list(self.edits))
        self._restore(self._future.pop())
        return True

    def _remember(self) -> None:
        self._past.append(list(self.edits))
        del self._past[:-self.HISTORY]
        self._future.clear()

    def _restore(self, state: list[Any]) -> None:
        self.edits[:] = state
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


class SculptTool(ToolMode):
    """Raising and lowering the land with the pointer.

    * **Left drag** raises the ground under the brush; **right drag** lowers it.
    * **The wheel** makes the brush wider or narrower.
    * **``[`` and ``]``** change how hard it pushes.
    * **Escape** abandons the stroke in progress.
    """

    def __init__(self, editor: LandEditor, **named: Any) -> None:
        named.setdefault('name', 'sculpt')
        named.setdefault('label', 'Sculpt land')
        super().__init__(**named)
        self.editor = editor
        self._lowering = False
        self._working = False

    def leave(self) -> None:
        """Another tool has the pointer: take the ring off the map."""
        self.editor.at = None

    def cancel(self) -> None:
        if self._working:
            self.editor.abandon()
        self._working = False

    def on_move(self, pointer: Pointer) -> bool:
        if not pointer.on_surface:
            return False
        self.editor.hover(pointer.world)
        return True

    def on_press(self, pointer: Pointer) -> bool:
        if not pointer.on_surface:
            return False
        self._lowering = pointer.button == 2
        self._working = True
        self.editor.begin(pointer.world, lower=self._lowering)
        return True

    def on_drag(self, pointer: Pointer) -> bool:
        if not self._working or not pointer.on_surface:
            return False
        self.editor.move(pointer.world, lower=self._lowering)
        return True

    def on_release(self, pointer: Pointer) -> bool:
        taken, self._working = self._working, False
        return taken

    def on_key(self, name: str, modifiers: tuple[int, int, int]) -> bool:
        if name == ']':
            self.editor.press_harder(1)
            return True
        if name == '[':
            self.editor.press_harder(-1)
            return True
        return False

    def on_wheel(self, pointer: Pointer, notches: int) -> bool:
        """The wheel sizes the brush rather than the map.

        A designer sculpting is choosing how much ground a stroke covers far
        more often than how much of the map they can see, and reaching for a
        key to do it puts the gesture down.
        """
        self.editor.grow(notches)
        return True

    # -- taking it back -----------------------------------------------------
    def undo(self) -> bool:
        return bool(self.editor.undo())

    def redo(self) -> bool:
        return bool(self.editor.redo())
