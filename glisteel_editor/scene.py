"""What the plan view draws: the land, the line, the road it makes, and what
carries it.

Three things, and each is rebuilt on a different schedule, because they cost
different amounts. The **land** is a second of arithmetic and is meshed once per
landscape. The **road** is the generator's whole job -- settling an alignment,
cutting the earthworks -- and is rebuilt when the line settles rather than while
it is being dragged. The **line and its markers** are a handful of vertices and
are rebuilt every time anything moves, which is what the designer is actually
watching.

The ground drawn is the ground that will be *baked*, earthworks and all: a
designer who cannot see the cutting cannot see what the line is doing to the
landscape. For the same reason the **structures** are drawn over the line: where
a road is carried on a deck or through a bore is the most expensive decision the
line makes, and from above the carriageway alone says nothing about it.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.basenodes import Box, Coordinate, IndexedLineSet
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
from OpenGLContext.scenegraph.pbrmesh import PBRMesh
from OpenGLContext.scenegraph.road import road_mesh
from OpenGLContext.scenegraph.shape import Shape
from OpenGLContext.scenegraph.transform import Transform

from glisteel_editor.project import Project

__all__ = ['MapScene']

#: Ground samples across the whole landscape for the editor's own mesh. Not a
#: tile's resolution: this is one mesh over the lot, at the detail a plan view
#: reads at, and the baker meshes it properly per tile afterwards.
GROUND_RESOLUTION = 129

#: How many pixels across a control point is drawn, whatever the zoom. A marker
#: fixed in metres disappears at the scale a whole circuit is drawn at.
MARKER_PIXELS = 9.0

#: How far above the ground the line and its markers float, in metres, so they
#: are not buried by the surface they describe.
LIFT = 3.0

#: How finely the road is re-sampled for the preview. Coarser than a baked
#: tile: this is a picture of where the road goes, not the road.
PREVIEW_SPACING = 8.0

#: How the stretches that are not plain road are marked, over the line. A
#: designer reads these as cost: a deck and a bore are what a line crossing the
#: wrong ground turns into.
STRUCTURE_COLOURS = {
    'bridge': (0.35, 0.80, 1.00),
    'tunnel': (1.00, 0.45, 0.35),
    'causeway': (0.55, 0.95, 0.60),
}

#: How far above the ground the structure marks float, over the line itself,
#: and how wide they are drawn as a multiple of the road's own width -- wider,
#: because at the scale a whole circuit is drawn at a road is a hairline.
STRUCTURE_LIFT = LIFT * 1.6
STRUCTURE_WIDTH = 4.0

MARKER_COLOUR = (0.95, 0.75, 0.20)
HOVERED_COLOUR = (1.0, 0.35, 0.25)
LINE_COLOUR = (1.0, 0.85, 0.35)


class MapScene:
    """The scenegraph the editor's plan view draws, built from a project."""

    def __init__(self, project: Project,
                 resolution: int = GROUND_RESOLUTION) -> None:
        self.project = project
        self.resolution = int(resolution)
        self._ground: Shape | None = None
        self._road: Shape | None = None
        self._structures: Shape | None = None
        self._world: Any = None
        #: The road surface, built once: it paints a 512-pixel texture, and the
        #: road is rebuilt every time the line settles.
        self._tarmac: Any = None

    # -- the world the project describes ----------------------------------
    def world(self) -> Any:
        """The project's world, kept until something about it changes."""
        if self._world is None:
            self._world = self.project.world()
        return self._world

    def reset(self) -> None:
        """Forget everything derived: the project has changed underneath."""
        self._ground = None
        self._road = None
        self._structures = None
        self._world = None

    def route_changed(self) -> None:
        """The line moved: the road and the ground it cuts are out of date."""
        self._ground = None
        self._road = None
        self._structures = None
        self._world = None

    def height_at(self, x: Any, z: Any) -> Any:
        """The ground as it will be baked, earthworks included."""
        return float(np.asarray(self.world().height_fn()(
            np.asarray([x], 'd'), np.asarray([z], 'd')))[0])

    def natural_height_at(self, x: Any, z: Any) -> Any:
        """The ground as the landscape has it, before any road was drawn."""
        from OpenGLContext.loaders.tiles3d.procedural import terrain_height
        return float(np.asarray(terrain_height(np.asarray([x], 'd'),
                                               np.asarray([z], 'd')))[0])

    # -- the land ----------------------------------------------------------
    def ground(self) -> Shape:
        """The landscape as one mesh, coloured the way the baked world is."""
        if self._ground is None:
            from OpenGLContext.loaders.tiles3d.procedural import (
                WATER_LEVEL,
                terrain_colors,
                terrain_patch,
            )
            half = self.project.landscape.extent / 2.0
            positions, normals, colors, indices = terrain_patch(
                -half, half, -half, half, self.resolution,
                height_fn=self.world().height_fn(), water_level=WATER_LEVEL,
                color_fn=terrain_colors)
            self._ground = Shape(
                geometry=PBRMesh(positions=positions, normals=normals,
                                 colors=colors, indices=indices),
                appearance=Appearance(material=PBRMaterial(
                    baseColor=(1.0, 1.0, 1.0), metallic=0.0, roughness=0.95)))
        return self._ground

    # -- the road ----------------------------------------------------------
    def road(self) -> Shape | None:
        """The road the line makes, or None while there is not enough line."""
        if self._road is None:
            route = self.project.route()
            if route is None or not route.is_road():
                return None
            path = self.world().circuit()
            if self._tarmac is None:
                from OpenGLContext.scenegraph.road import tarmac_material
                self._tarmac = tarmac_material()
            mesh = road_mesh(path.resampled(PREVIEW_SPACING), path.profile,
                             material=self._tarmac)
            self._road = Shape(geometry=mesh,
                               appearance=Appearance(material=self._tarmac))
        return self._road

    # -- what carries the road --------------------------------------------
    def structures(self) -> Shape | None:
        """The stretches of the line that are a deck, a bore or a causeway.

        One coloured line per stretch, over the road it replaces: the plan view
        is where a designer decides whether a route is worth what it costs, and
        from above a viaduct looks exactly like a road.
        """
        if self._structures is not None:
            return self._structures
        route = self.project.route()
        if route is None or not route.is_road():
            return None
        path = self.world().circuit()
        half = path.profile.total_width * STRUCTURE_WIDTH / 2.0
        points: list[list[float]] = []
        colours: list[tuple[float, float, float, float]] = []
        faces: list[int] = []
        for kind, start, end in path.structure_runs():
            run = path.points[(path.stations >= start)
                              & (path.stations <= end)][::2]
            if len(run) < 2:
                continue
            colour = STRUCTURE_COLOURS.get(str(kind), MARKER_COLOUR) + (1.0,)
            first = len(points)
            step = np.diff(run[:, [0, 2]], axis=0, append=run[-1:, [0, 2]])
            across = np.stack([-step[:, 1], step[:, 0]], axis=-1)
            across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True),
                                 1e-9)
            for (x, _y, z), (ax, az) in zip(run, across, strict=True):
                lift = self.height_at(x, z) + STRUCTURE_LIFT
                points.append([float(x - ax * half), lift, float(z - az * half)])
                points.append([float(x + ax * half), lift, float(z + az * half)])
                colours.extend((colour, colour))
            for step_index in range(len(run) - 1):
                a = first + step_index * 2
                faces.extend((a, a + 1, a + 2, a + 1, a + 3, a + 2))
        if not faces:
            return None
        self._structures = Shape(
            geometry=PBRMesh(positions=np.asarray(points, 'f'),
                             colors=np.asarray(colours, 'f'),
                             indices=np.asarray(faces, np.uint32)),
            appearance=Appearance(material=PBRMaterial(
                baseColor=(1.0, 1.0, 1.0), emissiveColor=(1.0, 1.0, 1.0),
                metallic=0.0, roughness=1.0, unlit=True, doubleSided=True)))
        return self._structures

    def structure_counts(self) -> dict[str, int]:
        """How many of each kind the line has on it, for the read-outs."""
        route = self.project.route()
        if route is None or not route.is_road():
            return {}
        found: dict[str, int] = {}
        for kind, _start, _end in self.world().circuit().structure_runs():
            found[str(kind)] = found.get(str(kind), 0) + 1
        return found

    # -- the line the designer drew ---------------------------------------
    def guide(self) -> Shape | None:
        """The drawn line itself, joining the points in the order drawn."""
        route = self.project.route()
        if route is None or len(route.points) < 2:
            return None
        points = [(x, self.height_at(x, z) + LIFT, z) for x, z in route.points]
        index = list(range(len(points)))
        if route.closed:
            index.append(0)
        index.append(-1)
        return Shape(
            geometry=IndexedLineSet(
                coord=Coordinate(point=points), coordIndex=index,
                color=None),
            appearance=Appearance(material=PBRMaterial(
                baseColor=LINE_COLOUR, emissiveColor=LINE_COLOUR,
                metallic=0.0, unlit=True)))

    def markers(self, metres_per_pixel: float,
                hovered: int | None = None) -> Group:
        """A handle at every control point, a fixed size on the screen."""
        route = self.project.route()
        size = float(metres_per_pixel) * MARKER_PIXELS
        children = []
        for index, (x, z) in enumerate(route.points if route else ()):
            colour = HOVERED_COLOUR if index == hovered else MARKER_COLOUR
            children.append(Transform(
                translation=(x, self.height_at(x, z) + LIFT, z),
                children=[Shape(
                    geometry=Box(size=(size, size, size)),
                    appearance=Appearance(material=PBRMaterial(
                        baseColor=colour, emissiveColor=colour,
                        metallic=0.0, unlit=True)))]))
        return Group(children=children)

    # -- all of it ---------------------------------------------------------
    def build(self, metres_per_pixel: float,
              hovered: int | None = None) -> Group:
        """Everything the plan view draws, as one group to mount."""
        children: list[Any] = [self.ground()]
        road = self.road()
        if road is not None:
            children.append(road)
        guide = self.guide()
        if guide is not None:
            children.append(guide)
        structures = self.structures()
        if structures is not None:
            children.append(structures)
        children.append(self.markers(metres_per_pixel, hovered))
        return Group(children=children)
