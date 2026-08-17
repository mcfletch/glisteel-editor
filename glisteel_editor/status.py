"""What the editor tells the designer, and where on the screen it goes.

Five things, and each answers a question that is otherwise a guess: which track
this is and whether it is saved; how long the line is, because that is the
question a circuit exists to answer; the scale, because a plan view with no
scale is a picture; which tool has the pointer; and whatever just happened.
"""
from __future__ import annotations

from typing import Any

from OpenGLContext.ui.hudwidgets import HUDGroup, HUDLayer, Readout

__all__ = ['EditorStatus']


class EditorStatus(HUDLayer):
    """The editor's read-outs. Call :meth:`show` when something changes."""

    def __init__(self, **named: Any) -> None:
        super().__init__(**named)
        self.title = Readout(label='TRACK')
        self.route = Readout(label='ROUTE')
        self.scale = Readout(label='SCALE')
        self.tool = Readout(anchor='bottom-left', label='TOOL')
        self.note = Readout(anchor='bottom-right', align='right', value='')
        # One block in the corner: anchored separately they would each take the
        # same corner and be drawn over one another.
        self.corner = HUDGroup(anchor='top-left',
                               children=[self.title, self.route, self.scale])
        self.children = [self.corner, self.tool, self.note]

    @property
    def message(self) -> str:
        """The last thing that happened, shown until the next thing does."""
        return str(self.note.value)

    @message.setter
    def message(self, text: str) -> None:
        self.note.value = str(text)

    def show(self, title: str = '', points: int = 0, length: float = 0.0,
             scale: float = 1.0, tool: str = '',
             structures: dict[str, int] | None = None) -> None:
        """Put the current state on the read-outs.

        ``structures`` is what the line has on it, by kind. A length on its own
        says nothing about the third of a route that is a viaduct, and that is
        the expensive third.
        """
        self.title.value = title
        self.route.value = '%d points, %s%s' % (points, _distance(length),
                                                _built(structures))
        self.scale.value = '%s / pixel' % _distance(scale, small=True)
        self.tool.value = tool


def _built(structures: dict[str, int] | None) -> str:
    """What is on the line, as a person would read it out.

    In a settled order rather than the dictionary's, so a rebuild that happens
    to enumerate them the other way does not make the label flicker.
    """
    if not structures:
        return ''
    said = ['%d %s%s' % (count, kind, '' if count == 1 else 's')
            for kind, count in sorted(structures.items()) if count]
    return ' -- ' + ', '.join(said) if said else ''


def _distance(metres: float, small: bool = False) -> str:
    """A distance as a person would say it."""
    metres = float(metres)
    if metres >= 1000.0:
        return '%.2f km' % (metres / 1000.0)
    if small and metres < 10.0:
        return '%.2f m' % metres
    return '%.0f m' % metres
