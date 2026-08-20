"""How much ground the plan view meshes, and how finely.

The landscape is kilometres across and the screen is a thousand pixels. Meshing
all of it at one resolution makes the detail wrong at every zoom but one: too
coarse to see a river bed or a sculpted hill when you are close, and more
triangles than pixels when you are not. It is the same problem a streamed world
answers with tiles, and the same answer works for a preview -- **mesh the ground
being looked at, at the detail the screen can show**.

A :class:`GroundPatch` is that decision: which rectangle, and how many samples
across it. It is deliberately a value with no geometry in it, so what to mesh
can be decided and asserted without meshing anything.

Two things keep it from thrashing. The patch is **bigger than the view**, so a
small pan is still inside what is already meshed; and it is kept until the view
leaves it or the scale changes by more than a step, so a wheel notch does not
re-mesh a landscape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ['GroundPatch', 'patch_for']

#: How much wider than the view the meshed ground is. A quarter again on each
#: side: enough that a pan of a few dozen pixels is already meshed, little
#: enough that most of what is meshed is on screen.
MARGIN = 1.5

#: How many pixels apart the samples are aimed at. Three is finer than the eye
#: resolves on a shaded surface and coarse enough that the mesh is a fraction
#: of the pixels it covers.
PIXELS_PER_SAMPLE = 3.0

#: How far the scale may move before the patch is remade, as a factor either
#: way. A wheel notch is a quarter; this is more than one notch and less than
#: three, so zooming does not re-mesh at every click and does not go two steps
#: stale either.
SCALE_STEP = 1.6


@dataclass(frozen=True)
class GroundPatch:
    """Which ground is meshed, and how finely.

    ``minimum`` and ``maximum`` are ``(x, z)`` in world metres and
    ``resolution`` is samples across each side.
    """

    minimum: tuple[float, float]
    maximum: tuple[float, float]
    resolution: int
    #: The scale it was chosen for, in metres a pixel, so a later view can ask
    #: whether it is still close enough.
    scale: float = 1.0
    #: Whether it already covers the whole landscape. There is nothing coarser
    #: to go to, so zooming out further must not ask for another.
    whole: bool = False

    #: The most and fewest samples a side. The ceiling is a vertex budget --
    #: a quarter of a million is a tenth of a second of arithmetic and fits in
    #: a buffer nobody notices -- and the floor is what stops a patch from
    #: being four vertices and a normal.
    FINEST = 385
    COARSEST = 33

    def spacing(self) -> float:
        """How far apart the samples are on the ground, in metres."""
        across = self.maximum[0] - self.minimum[0]
        return float(across) / max(self.resolution - 1, 1)

    def contains(self, centre: tuple[float, float], span: float) -> bool:
        """Whether a view of this centre and span is inside what is meshed."""
        half = float(span) / 2.0
        return bool(self.minimum[0] <= centre[0] - half
                    and self.maximum[0] >= centre[0] + half
                    and self.minimum[1] <= centre[1] - half
                    and self.maximum[1] >= centre[1] + half)

    def serves(self, centre: tuple[float, float], span: float,
               viewport: tuple[int, int], extent: float) -> bool:
        """Whether this patch is still the right one for a view.

        It is when the view is inside it *and* the scale has not moved more
        than a step. A patch that already covers the whole landscape serves any
        wider view as well, because there is nothing coarser to give.
        """
        wanted = _scale_for(span, viewport)
        near = (1.0 / SCALE_STEP) <= (wanted / max(self.scale, 1e-9)) <= SCALE_STEP
        if self.whole and wanted >= self.scale:
            return True
        return bool(near and self.contains(centre, span))


def _scale_for(span: float, viewport: tuple[int, int]) -> float:
    """Metres a pixel for a view of this span."""
    return float(span) / max(int(viewport[1]), 1)


def patch_for(centre: tuple[float, float], span: float,
              viewport: tuple[int, int], extent: float,
              margin: float = MARGIN,
              pixels_per_sample: float = PIXELS_PER_SAMPLE) -> GroundPatch:
    """Which ground to mesh for a view, and how finely.

    ``span`` is how many metres fit down the window, ``extent`` how many metres
    across the landscape is. The patch is square, because the map turns and the
    window resizes and a square survives both, and it is clipped to the
    landscape: there is no ground outside it to mesh.
    """
    half_world = float(extent) / 2.0
    wanted = float(span) * float(margin) / 2.0
    low_x = max(centre[0] - wanted, -half_world)
    high_x = min(centre[0] + wanted, half_world)
    low_z = max(centre[1] - wanted, -half_world)
    high_z = min(centre[1] + wanted, half_world)
    # Square, and centred on what is being looked at: the clip above may have
    # taken more off one side than the other.
    side = min(high_x - low_x, high_z - low_z)
    side = min(side, 2.0 * wanted)
    middle_x = min(max(centre[0], -half_world + side / 2.0),
                   half_world - side / 2.0)
    middle_z = min(max(centre[1], -half_world + side / 2.0),
                   half_world - side / 2.0)
    minimum = (middle_x - side / 2.0, middle_z - side / 2.0)
    maximum = (middle_x + side / 2.0, middle_z + side / 2.0)
    scale = _scale_for(span, viewport)
    # One sample every few pixels of the *window*, over the patch rather than
    # over the view -- the patch is larger, so it needs proportionally more.
    across_pixels = side / max(scale, 1e-9)
    resolution = int(math.ceil(across_pixels / max(pixels_per_sample, 0.5))) + 1
    resolution = max(GroundPatch.COARSEST,
                     min(GroundPatch.FINEST, resolution))
    return GroundPatch(minimum=minimum, maximum=maximum,
                       resolution=resolution, scale=scale,
                       whole=bool(side >= float(extent) - 1e-6))
