"""What the plan view draws: the land, its relief, the line, the road it makes,
and what carries it.

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

The land is read two ways at once, because either alone leaves a designer
guessing. **Shaded relief** puts a fixed low sun on the ground's own normals, so
a ridge and a valley are different colours rather than the same green; and
**contours** say by how much, which is what a road held to a grade is drawn
against. Both are turned off from the View menu when the line alone is what is
being read.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from OpenGLContext.edit.relief import shade_colors
from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.basenodes import Box, Coordinate, IndexedLineSet
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
from OpenGLContext.scenegraph.pbrmesh import PBRMesh
from OpenGLContext.scenegraph.road import (
    banked_sections,
    road_mesh,
    widened_sections,
)
from OpenGLContext.scenegraph.shape import Shape
from OpenGLContext.scenegraph.transform import Transform

from glisteel_editor.detail import GroundPatch, patch_for
from glisteel_editor.project import Project

__all__ = ['MapScene']


class _NotBuilt:
    """Stands for a cache that has not been filled yet.

    ``None`` cannot: it is also a perfectly good *answer* -- a flat circuit
    needs no bridge and no bore -- and a cache that cannot tell the two apart
    works the answer out again on every redraw, which for a structure means
    settling the whole alignment.
    """

    def __repr__(self) -> str:                   # pragma: no cover - a marker
        return 'NOT_BUILT'


NOT_BUILT = _NotBuilt()

#: Ground samples across the whole landscape when nobody has said where the
#: view is looking. The detail normally follows the zoom -- see
#: :mod:`glisteel_editor.detail` -- and this is what a scene meshes before it
#: has been told anything, and the floor a caller gets by asking for it.
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

#: The brush's ring: how many points it is drawn with, and its colour. A ring
#: rather than a filled disc, so the land it is about to change is still
#: visible through it.
BRUSH_POINTS = 72
BRUSH_COLOUR = (0.45, 0.95, 1.00)

#: How wide the start/finish bar is drawn, as a multiple of the road's width,
#: and its colour. Wider than the road because at the scale a whole circuit is
#: read at the road is a hairline.
START_WIDTH = 6.0
START_COLOUR = (1.0, 1.0, 1.0)

#: How the water is drawn **on the map**: blue, because that is what water is
#: on a map. Not the water a baked world gets, which is nearly black and takes
#: its brightness from the sky in it -- over a snowfield at a kilometre's range
#: that is a film nobody can see, and a map's job is to be read.
RIVER_COLOUR = (0.10, 0.35, 0.90)
SPRING_COLOUR = (0.55, 0.90, 1.00)

#: How far above the ground the water is drawn, in metres, and how many pixels
#: across a spring's marker is.
WATER_LIFT = LIFT * 0.8
SPRING_PIXELS = 7.0

#: How few pixels wide a river may be drawn. A map exaggerates what it has to
#: show: the ground here is meshed at a few hundred samples across a landscape
#: kilometres wide, so a river at its true width is two pixels and inside the
#: mesh. The baked world has it at its real size.
RIVER_PIXELS = 5.0

#: How far apart the iso-height lines are by default, in metres. Twenty-five is
#: the reading a whole circuit is drawn at: close enough that a hillside shows
#: several, far enough that a plain is not hatched.
CONTOUR_INTERVAL = 25.0

#: The spacings :meth:`MapScene.suggested_interval` chooses between, which are
#: the ones the interface offers. The coarse end is for mountain country, where
#: a spacing that reads on rolling hills draws a hatch.
CONTOUR_INTERVALS_OFFERED = (10.0, 25.0, 50.0, 100.0, 250.0)

#: How many samples across the landscape is read at to decide how tall it is.
#: Coarse on purpose: the answer settles a contour spacing, not a road.
RELIEF_SAMPLES = 65

#: How finely the height field is sampled to find those lines. Finer than the
#: ground mesh, because a contour is a line and its wobble is read directly,
#: whereas the mesh's is hidden by shading.
CONTOUR_RESOLUTION = 257

#: How far above the drawn ground the contours float, in metres, and what
#: colour they are: a dark line the yellow route reads over.
#:
#: Above the *drawn* ground rather than at their own elevation, because the
#: ground mesh is a few hundred samples across a landscape kilometres wide and
#: draws straight lines between them: over a rise it passes above the surface
#: it stands for, by metres, and a line at the true elevation disappears into
#: it. In a plan view the height a line is drawn at moves it nowhere, and its
#: elevation is what the map says rather than where the line is.
CONTOUR_LIFT = LIFT * 1.2
CONTOUR_COLOUR = (0.16, 0.19, 0.24)


class MapScene:
    """The scenegraph the editor's plan view draws, built from a project."""

    #: How many contours a map can carry before it stops being read as one.
    READABLE_CONTOURS = 14

    def __init__(self, project: Project,
                 resolution: int = GROUND_RESOLUTION,
                 hillshade: bool = True, show_contours: bool = True,
                 contour_interval: float = CONTOUR_INTERVAL) -> None:
        self.project = project
        self.resolution = int(resolution)
        self._ground: Shape | None = None
        self._road: Shape | None = None
        self._structures: Shape | None | _NotBuilt = NOT_BUILT
        self._contours: Group | None = None
        self._water: Group | None = None
        #: The scale the water's markers were last drawn for: they are a
        #: screen size, so a zoom rebuilds them.
        self._water_scale: float | None = None
        #: The heights the ground mesh is built from, for putting things on it.
        self._grid: Any = None
        #: Which ground is meshed and how finely; None until told where to look.
        self._patch: GroundPatch | None = None
        #: Water is one material for every river; it is built once.
        self._water_material: Any = None
        self._world: Any = None
        #: The road surface, built once: it paints a 512-pixel texture, and the
        #: road is rebuilt every time the line settles.
        self._tarmac: Any = None
        #: What the map is drawn at, so what it exaggerates follows the zoom.
        self._metres_per_pixel = 1.0
        self._hillshade = bool(hillshade)
        self._show_contours = bool(show_contours)
        self._contour_interval = float(contour_interval)

    # -- how the land is read ----------------------------------------------
    @property
    def hillshade(self) -> bool:
        """Whether the ground is shaded for relief rather than lit flat."""
        return self._hillshade

    @hillshade.setter
    def hillshade(self, on: bool) -> None:
        if bool(on) == self._hillshade:
            return
        self._hillshade = bool(on)
        self._ground = None

    @property
    def show_contours(self) -> bool:
        """Whether iso-height lines are drawn over the ground."""
        return self._show_contours

    @show_contours.setter
    def show_contours(self, on: bool) -> None:
        if bool(on) == self._show_contours:
            return
        self._show_contours = bool(on)
        self._contours = None

    @property
    def contour_interval(self) -> float:
        """How far apart the iso-height lines are, in metres."""
        return self._contour_interval

    @contour_interval.setter
    def contour_interval(self, metres: float) -> None:
        if float(metres) == self._contour_interval:
            return
        self._contour_interval = float(metres)
        self._contours = None

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
        self._structures = NOT_BUILT
        self._contours = None
        self._water = None
        self._grid = None
        self._world = None

    def water_changed(self) -> None:
        """A spring moved: the rivers, and the ground they cut, are out of date."""
        self._ground = None
        self._road = None
        self._structures = NOT_BUILT
        self._water = None
        self._grid = None
        self._world = None

    def route_changed(self) -> None:
        """The line moved: the road and the ground it cuts are out of date.

        The contours are not: they are the *landscape's* iso-heights, drawn
        before any road was put through it, so a road's earthworks do not
        redraw the map a designer is reading the land from.
        """
        self._ground = None
        self._road = None
        self._structures = NOT_BUILT
        self._world = None

    def drawn_height(self, x: Any, z: Any) -> Any:
        """The ground the plan view actually *draws*, at any point.

        Not the height function: the mesh is a few hundred samples across a
        landscape kilometres wide and draws straight lines between them, so
        over a valley it passes tens of metres above the surface it stands for.
        Anything laid on the ground -- a river, a contour, a marker -- has to be
        put on *that* surface or it is inside it.

        The same grid the mesh is built on, interpolated the way a triangle
        interpolates, so what this answers is what is on the screen.
        """
        patch = self.patch()
        steps = max(2, patch.resolution)
        spacing = patch.spacing()
        grid = self._ground_grid()
        at_x = np.clip((np.asarray(x, dtype='d') - patch.minimum[0]) / spacing,
                       0.0, steps - 1.0)
        at_z = np.clip((np.asarray(z, dtype='d') - patch.minimum[1]) / spacing,
                       0.0, steps - 1.0)
        low_x = np.clip(np.floor(at_x).astype(np.intp), 0, steps - 2)
        low_z = np.clip(np.floor(at_z).astype(np.intp), 0, steps - 2)
        along_x = at_x - low_x
        along_z = at_z - low_z
        near = (grid[low_x, low_z] * (1.0 - along_x)
                + grid[low_x + 1, low_z] * along_x)
        far = (grid[low_x, low_z + 1] * (1.0 - along_x)
               + grid[low_x + 1, low_z + 1] * along_x)
        drawn: np.ndarray = near * (1.0 - along_z) + far * along_z
        return drawn

    def _ground_grid(self) -> np.ndarray:
        """The heights the ground mesh is built from, sampled once and kept."""
        if self._grid is None:
            patch = self.patch()
            steps = max(2, patch.resolution)
            xs = np.linspace(patch.minimum[0], patch.maximum[0], steps)
            zs = np.linspace(patch.minimum[1], patch.maximum[1], steps)
            gx, gz = np.meshgrid(xs, zs, indexing='ij')
            self._grid = np.asarray(self.world().height_fn()(gx, gz),
                                    dtype='d')
        grid: np.ndarray = self._grid
        return grid

    def height_at(self, x: Any, z: Any) -> Any:
        """The ground as it will be baked, earthworks included, at one point.

        For one point. Anything asking about a *set* of them -- a line, its
        handles, a river, a ring -- wants :meth:`heights_at`: the height
        function is vectorised, and calling it once per point costs a
        multiple of what calling it once does.
        """
        return float(self.heights_at([x], [z])[0])

    def heights_at(self, x: Any, z: Any) -> np.ndarray:
        """The baked ground under each of these points, in one pass.

        The contours have always been drawn this way and say why: the height
        function is vectorised, and a line is hundreds of points. The line the
        designer is dragging is redrawn on every pointer movement, so this is
        the difference between a drag and a slideshow.
        """
        found: np.ndarray = np.asarray(
            self.world().height_fn()(np.asarray(x, dtype='d'),
                                     np.asarray(z, dtype='d')), dtype='d')
        return found

    def natural_height_at(self, x: Any, z: Any) -> Any:
        """The ground the height source has, before any road was drawn.

        The landscape's own edits are part of it: a hill a designer raised is
        the land, and only the road's earthworks are not.
        """
        return float(np.asarray(self.world().natural()(
            np.asarray([x], 'd'), np.asarray([z], 'd')))[0])

    # -- the land ----------------------------------------------------------
    # -- how much ground, and how finely -----------------------------------
    def viewing(self, centre: tuple[float, float], span: float,
                viewport: tuple[int, int]) -> bool:
        """Say where the map is looking, so the ground can follow it.

        The landscape is kilometres across and the screen is a thousand pixels:
        one mesh over the lot is too coarse to see a river bed when you are
        close and more triangles than pixels when you are not. So the ground
        that is meshed is the ground being looked at, at the detail the screen
        can show -- and the coarse mesh is swapped out for a finer one over
        less ground as the view comes in.

        Answers whether anything changed, so a caller knows to rebuild.
        """
        if self._patch is not None and self._patch.serves(
                centre, span, viewport, self.project.landscape.extent):
            return False
        self._patch = patch_for(centre, span, viewport,
                                self.project.landscape.extent)
        self._ground = None
        self._grid = None
        self._contours = None
        self._water = None
        return True

    def patch(self) -> GroundPatch:
        """The ground that is meshed, and how finely.

        A scene nobody has told where to look meshes the whole landscape at
        the resolution it was made with, which is what a headless caller and
        the first frame both want.
        """
        if self._patch is None:
            half = self.project.landscape.extent / 2.0
            self._patch = GroundPatch(minimum=(-half, -half),
                                      maximum=(half, half),
                                      resolution=self.resolution, whole=True)
        return self._patch

    def ground(self) -> Shape:
        """The ground being looked at, coloured the way the baked world is.

        With shading on, the relief is worked into those colours against a
        fixed low sun and the mesh is drawn unlit: a map is read rather than
        admired, and a light in the scene would shade it a second time.
        """
        if self._ground is None:
            from OpenGLContext.loaders.tiles3d.procedural import (
                WATER_LEVEL,
                terrain_colors,
                terrain_patch,
            )
            patch = self.patch()
            positions, normals, colors, indices = terrain_patch(
                patch.minimum[0], patch.maximum[0],
                patch.minimum[1], patch.maximum[1], patch.resolution,
                height_fn=self.world().height_fn(), water_level=WATER_LEVEL,
                color_fn=terrain_colors)
            if self._hillshade:
                colors = shade_colors(colors, normals)
            self._ground = Shape(
                geometry=PBRMesh(positions=positions, normals=normals,
                                 colors=colors, indices=indices),
                appearance=Appearance(material=PBRMaterial(
                    baseColor=(1.0, 1.0, 1.0), metallic=0.0, roughness=0.95,
                    unlit=self._hillshade)))
        return self._ground

    # -- how high the land is ----------------------------------------------
    def relief(self) -> tuple[float, float]:
        """The lowest and highest ground in the landscape, in metres.

        Sampled coarsely: this decides how closely to describe the land, and a
        few metres either way changes nothing about that answer.
        """
        half = self.project.landscape.extent / 2.0
        axis = np.linspace(-half, half, RELIEF_SAMPLES)
        x, z = np.meshgrid(axis, axis, indexing='ij')
        ground = np.asarray(self.world().natural()(x, z), dtype='d')
        return (float(ground.min()), float(ground.max()))

    def suggested_interval(self,
                           offered: Sequence[float] = CONTOUR_INTERVALS_OFFERED
                           ) -> float:
        """The finest of ``offered`` that still draws a map somebody can read.

        A spacing that suits rolling hills turns a mountain range into a hatch,
        and one that suits a range leaves a plain with two lines on it. So the
        landscape chooses: the closest description that stays under
        :attr:`READABLE_CONTOURS` lines.
        """
        from OpenGLContext_editor.world.contours import contour_levels
        low, high = self.relief()
        for interval in sorted(offered):
            if len(contour_levels(low, high, interval)) <= self.READABLE_CONTOURS:
                return float(interval)
        return float(max(offered))

    def contours(self) -> Group | None:
        """The iso-height lines of the landscape, or None when they are off.

        Of the *landscape*, not of the baked ground: a contour is what a
        designer measures a gradient against, and one that jumped every time
        the road's earthworks moved would be measuring the road.
        """
        if not self._show_contours:
            return None
        if self._contours is None:
            from OpenGLContext_editor.world.contours import contours_of
            patch = self.patch()
            side = patch.maximum[0] - patch.minimum[0]
            centre = ((patch.minimum[0] + patch.maximum[0]) / 2.0,
                      (patch.minimum[1] + patch.maximum[1]) / 2.0)
            found = contours_of(self.world().natural(), extent=side,
                                interval=self._contour_interval,
                                resolution=CONTOUR_RESOLUTION, centre=centre)
            children = [self._contour_shape(contour) for contour in found]
            self._contours = Group(children=[child for child in children
                                             if child is not None])
        return self._contours

    def _contour_shape(self, contour: Any) -> Shape | None:
        """One elevation's lines, as a single line set over the ground."""
        drawn = [line for line in contour.lines if len(line) >= 2]
        if not drawn:
            return None
        flat = np.vstack(drawn)
        # One call for the whole elevation rather than one a vertex: the height
        # function is vectorised, and a contour is thousands of points.
        lifted = np.asarray(self.world().height_fn()(flat[:, 0], flat[:, 1]),
                            dtype='d') + CONTOUR_LIFT
        points = np.stack([flat[:, 0], lifted, flat[:, 1]], axis=1)
        index: list[int] = []
        at = 0
        for line in drawn:
            index.extend(range(at, at + len(line)))
            index.append(-1)
            at += len(line)
        return Shape(
            geometry=IndexedLineSet(coord=Coordinate(point=points),
                                    coordIndex=index, color=None),
            appearance=Appearance(material=PBRMaterial(
                baseColor=CONTOUR_COLOUR, emissiveColor=CONTOUR_COLOUR,
                metallic=0.0, unlit=True)))

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
            line = path.resampled(PREVIEW_SPACING)
            # The preview is the road the bake will build, banked corners and
            # all: a designer who is shown a flat road cannot see what the
            # corners they drew are going to be to drive.
            stations = np.linspace(0.0, path.length, len(line))
            bank = path.bank_at(stations)
            sections = widened_sections(
                np.tile(path.profile.section(), (len(line), 1, 1)),
                path.widening_at(stations), path.profile)
            sections = banked_sections(sections, bank, path.profile)
            mesh = road_mesh(line, path.profile, material=self._tarmac,
                             sections=sections, bank=bank)
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
        if self._structures is not NOT_BUILT:
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
            self._structures = None              # nothing to draw is an answer
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

    # -- where a lap begins -------------------------------------------------
    def start_mark(self, metres_per_pixel: float) -> Shape | None:
        """A bar across the line where a lap begins, or None with no line.

        Across rather than along: a mark along the road is a road marking, and
        what a designer is looking for is the one place on the circuit the
        timing counts from.
        """
        route = self.project.route()
        if route is None or not route.points:
            return None
        where = route.start_point()
        if where is None:
            return None
        along = self._heading(route)
        across = np.array([-along[1], along[0]])
        half = self.world().circuit().profile.total_width \
            * START_WIDTH / 2.0 if route.is_road() else \
            float(metres_per_pixel) * MARKER_PIXELS * 3.0
        ends = [(where[0] - across[0] * half, where[1] - across[1] * half),
                (where[0] + across[0] * half, where[1] + across[1] * half)]
        points = [(x, self.height_at(x, z) + STRUCTURE_LIFT, z)
                  for x, z in ends]
        return Shape(
            geometry=IndexedLineSet(coord=Coordinate(point=points),
                                    coordIndex=[0, 1, -1], color=None),
            appearance=Appearance(material=PBRMaterial(
                baseColor=START_COLOUR, emissiveColor=START_COLOUR,
                metallic=0.0, unlit=True)))

    @staticmethod
    def _heading(route: Any) -> np.ndarray:
        """Which way the road runs at the start, as a unit vector."""
        plan = np.asarray(route.points, dtype='d').reshape(-1, 2)
        index = int(route.start) if 0 <= int(route.start) < len(plan) else 0
        ahead = plan[(index + 1) % len(plan)] if len(plan) > 1 else plan[index]
        behind = plan[index - 1] if len(plan) > 1 else plan[index]
        step = ahead - behind
        length = float(np.linalg.norm(step))
        return step / length if length > 1e-9 else np.array([1.0, 0.0])

    # -- the water ---------------------------------------------------------
    def water(self, metres_per_pixel: float = 1.0) -> Group | None:
        """The rivers and the springs they come out of, or None where none are.

        The river is drawn as the line the water takes rather than as a
        surface: what a designer is deciding is where it runs and what the road
        has to do about it, and a sheet over the bed hides the bed.
        """
        if not self.project.landscape.springs:
            return None
        if self._water is None or self._water_scale != float(metres_per_pixel):
            self._water_scale = float(metres_per_pixel)
            self._water = None
        if self._water is None:
            children: list[Any] = []
            for channel in self.project.landscape.channels():
                shape = self._river_shape(channel)
                if shape is not None:
                    children.append(shape)
            children.extend(self._spring_marks(metres_per_pixel))
            self._water = Group(children=children)
        return self._water

    def _river_shape(self, channel: Any) -> Shape | None:
        """One river: the water surface itself, not a line standing for one.

        As wide as the bed is, or as wide as the map needs it to be read at
        this zoom, so a river carrying more reads as a bigger river. Drawn in
        **map** water rather than in the water a baked world gets: real water
        is nearly black and takes its brightness from the sky in it, which over
        a snowfield at a kilometre's range is a film nobody can see.
        """
        # On the ground the map *draws*, not in the bed the world will have:
        # the plan view's mesh cannot hold a channel this narrow, so a river at
        # its true depth is buried in the ground above it.
        surface = channel.surface(
            self.drawn_height, lift=WATER_LIFT, on_gpu=True,
            width=np.maximum(channel.widths(), self._river_width()))
        if surface is None:
            return None
        if self._water_material is None:
            self._water_material = PBRMaterial(
                baseColor=RIVER_COLOUR, emissiveColor=RIVER_COLOUR,
                metallic=0.0, roughness=0.4, unlit=True)
        surface.material = self._water_material
        return Shape(geometry=surface,
                     appearance=Appearance(material=self._water_material))

    def _river_width(self) -> float:
        """How narrow a river may be drawn, in metres at the current scale."""
        return float(self._metres_per_pixel) * RIVER_PIXELS

    def _spring_marks(self, metres_per_pixel: float = 1.0) -> list[Any]:
        """A mark at every spring, so one on flat ground is still findable."""
        size = float(metres_per_pixel) * SPRING_PIXELS
        marks = []
        for spring in self.project.landscape.springs:
            x, z = spring.at
            marks.append(Transform(
                translation=(x, self.height_at(x, z) + WATER_LIFT, z),
                children=[Shape(
                    geometry=Box(size=(size, size, size)),
                    appearance=Appearance(material=PBRMaterial(
                        baseColor=SPRING_COLOUR, emissiveColor=SPRING_COLOUR,
                        metallic=0.0, unlit=True)))]))
        return marks

    def advance(self, when: float) -> bool:
        """Move the water on. True if anything on screen changed.

        The card does the moving: the surfaces were uploaded once and this is
        the one number they are drawn from, so a flowing river costs a uniform
        a frame rather than a re-meshing.
        """
        water = self._water
        if water is None:
            return False
        moved = False
        for child in water.children:
            surface = getattr(child, 'geometry', None)
            if surface is None:                  # a marker rather than a sheet
                continue
            if getattr(surface, 'wave_style', None) is not None:
                surface.wave_time = float(when)
                moved = True
        return moved

    # -- what the brush is about to do -------------------------------------
    def brush(self, centre: tuple[float, float], radius: float) -> Shape:
        """A ring on the ground showing where a stroke would land.

        Draped over the ground rather than drawn flat at one height, so on a
        hillside the ring says which ground it covers instead of disappearing
        into the slope.
        """
        angles = np.linspace(0.0, 2.0 * np.pi, BRUSH_POINTS + 1)
        x = float(centre[0]) + float(radius) * np.cos(angles)
        z = float(centre[1]) + float(radius) * np.sin(angles)
        y = np.asarray(self.world().height_fn()(x, z), dtype='d') + LIFT
        points = np.stack([x, y, z], axis=1)
        return Shape(
            geometry=IndexedLineSet(
                coord=Coordinate(point=points),
                coordIndex=[*range(len(points)), -1], color=None),
            appearance=Appearance(material=PBRMaterial(
                baseColor=BRUSH_COLOUR, emissiveColor=BRUSH_COLOUR,
                metallic=0.0, unlit=True)))

    # -- the line the designer drew ---------------------------------------
    def guide(self) -> Shape | None:
        """The drawn line itself, joining the points in the order drawn."""
        route = self.project.route()
        if route is None or len(route.points) < 2:
            return None
        flat = np.asarray(route.points, dtype='d').reshape(-1, 2)
        lifted = self.heights_at(flat[:, 0], flat[:, 1]) + LIFT
        points = [(float(x), float(y), float(z))
                  for (x, z), y in zip(flat, lifted, strict=True)]
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
        drawn = route.points if route else []
        if not drawn:
            return Group(children=[])
        flat = np.asarray(drawn, dtype='d').reshape(-1, 2)
        lifted = self.heights_at(flat[:, 0], flat[:, 1]) + LIFT
        children = []
        for index, ((x, z), y) in enumerate(zip(flat, lifted, strict=True)):
            colour = HOVERED_COLOUR if index == hovered else MARKER_COLOUR
            children.append(Transform(
                translation=(float(x), float(y), float(z)),
                children=[Shape(
                    geometry=Box(size=(size, size, size)),
                    appearance=Appearance(material=PBRMaterial(
                        baseColor=colour, emissiveColor=colour,
                        metallic=0.0, unlit=True)))]))
        return Group(children=children)

    # -- all of it ---------------------------------------------------------
    def build(self, metres_per_pixel: float, hovered: int | None = None,
              brush: tuple[tuple[float, float], float] | None = None) -> Group:
        """Everything the plan view draws, as one group to mount.

        ``brush`` is where a sculpting stroke would land, as a centre and a
        radius, or None when no brush is in force.
        """
        if float(metres_per_pixel) != self._metres_per_pixel:
            # What a map exaggerates follows its scale: a river drawn five
            # pixels wide is a different number of metres at every zoom.
            self._metres_per_pixel = float(metres_per_pixel)
            self._water = None
        children: list[Any] = [self.ground()]
        contours = self.contours()
        if contours is not None:
            children.append(contours)
        road = self.road()
        if road is not None:
            children.append(road)
        guide = self.guide()
        if guide is not None:
            children.append(guide)
        structures = self.structures()
        if structures is not None:
            children.append(structures)
        water = self.water(metres_per_pixel)
        if water is not None:
            children.append(water)
        start = self.start_mark(metres_per_pixel)
        if start is not None:
            children.append(start)
        children.append(self.markers(metres_per_pixel, hovered))
        if brush is not None:
            children.append(self.brush(brush[0], brush[1]))
        return Group(children=children)
