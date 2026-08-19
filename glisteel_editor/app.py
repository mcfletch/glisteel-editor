"""The track editor: draw a circuit on a landscape and bake a world to drive.

    glisteel-editor                    # a fresh landscape to draw on
    glisteel-editor monaco.glisteel    # carry on with a track

The window is a **map**: the landscape from straight above, orthographic, so a
metre is the same number of pixels wherever it is and the line drawn on it is
the line the world gets. Left-click on the ground puts a point down; on the
line, puts one in between; on a point, drags it. Right-click a point takes it
out. The road settles onto the land as soon as the pointer is let go, and what
is drawn is the ground *with its earthworks*, so a cutting is something a
designer can see rather than something they find out about later.

Keys::

    left drag / arrows   move a control point, or the map
    right drag           pan the map
    wheel                zoom about the pointer
    f                    frame the whole landscape
    delete               remove the point under the pointer
    ctrl-z / ctrl-y      undo, redo
    ctrl-s / ctrl-o      save / open
    ctrl-b               bake a world
    ctrl-d               drive what was baked
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

os.environ.setdefault('OPENGLCONTEXT_PROFILE', 'core')
os.environ.setdefault('OPENGLCONTEXT_BACKEND', 'glfw')
os.environ.setdefault('OPENGLCONTEXT_RENDERER', 'pbr')

from OpenGLContext import testingcontext  # noqa: E402
from OpenGLContext.edit.mapview import MapView, MapViewPlatform  # noqa: E402
from OpenGLContext.edit.orbitview import OrbitView, OrbitViewPlatform  # noqa: E402
from OpenGLContext.scenegraph.scenegraph import SceneGraph  # noqa: E402
from OpenGLContext.ui import dialogs  # noqa: E402
from OpenGLContext.ui.menu import MenuBar, MenuItem  # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin  # noqa: E402
from OpenGLContext.ui.toolpalette import ToolPalette  # noqa: E402
from OpenGLContext.ui.widgets import Separator  # noqa: E402
from OpenGLContext.viewer import environment  # noqa: E402
from OpenGLContext.viewer.sceneviewer import ViewerContext  # noqa: E402

from glisteel_editor.controls import (  # noqa: E402
    ZOOM_STEP,
    MapControls,
    OrbitControls,
)
from glisteel_editor.editing import RouteEditor, editor_tools  # noqa: E402
from glisteel_editor.project import Project, new_project  # noqa: E402
from glisteel_editor.scene import (  # noqa: E402
    CONTOUR_INTERVAL,
    CONTOUR_INTERVALS_OFFERED,
    MapScene,
)
from glisteel_editor.sculpting import LandEditor  # noqa: E402
from glisteel_editor.status import EditorStatus  # noqa: E402
from glisteel_editor.water import WaterEditor  # noqa: E402

log = logging.getLogger(__name__)

BaseContext: Any = testingcontext.getInteractive()

#: How the world is lit for the map. Bright and from high up: a plan view is
#: read, not admired, and long shadows across it hide the line.
LIGHT_SCALE = 400.0

#: How much of the top of the window the menu bar takes, in reference pixels,
#: so the read-outs start below it rather than under it.
MENU_BAR_ROOM = 30.0

#: The default name a bake is written under, beside the project file.
BAKE_SUFFIX = '-world'

#: The contour spacings the View menu offers, in metres. A ladder rather than a
#: number to type: a designer chooses how densely the land is described, and
#: the useful settings for a track a few kilometres round are a handful.
CONTOUR_INTERVALS = CONTOUR_INTERVALS_OFFERED


class EditorContext(OverlayMixin, BaseContext):    # pragma: no cover - needs a window
    """The editor's window: a map, a menu bar, and the tools in between."""

    config: Any = None

    def OnInit(self) -> None:
        self.project = self.config.project
        #: How the land is read, which follows the project rather than being
        #: part of it: a designer's choice about the map, not about the track.
        self.view_options: dict[str, Any] = {
            'hillshade': True, 'show_contours': True,
            'contour_interval': CONTOUR_INTERVAL}
        self.scene = MapScene(self.project, **self.view_options)
        self.view_options['contour_interval'] = self.scene.suggested_interval()
        self.scene.contour_interval = self.view_options['contour_interval']
        self.view = MapView(centre=(0.0, 0.0),
                            span=self.project.landscape.extent)
        # The platform the context made for itself is a perspective camera;
        # this one reads the map. It has to be told the window's size, because
        # the context told the one it is replacing and will not do it again
        # until the window is resized.
        self.mapPlatform = MapViewPlatform(self.view, self.getViewPort())
        self.platform = self.mapPlatform
        self.platform.setViewport(*self.getViewPort())
        self.editor = RouteEditor(
            self._route(), on_change=self._route_changed,
            height_fn=lambda x, z: self.scene.world().natural()(x, z),
            snap_interval=self.view_options['contour_interval'])
        self.land = LandEditor(self.project.landscape,
                               on_change=self._land_changed)
        self.water = WaterEditor(self.project.landscape,
                                 on_change=self._land_changed)
        self.tools = editor_tools(self.editor, self.view, self.getViewPort,
                                  on_change=self._map_moved,
                                  on_tool=self._tool_changed, land=self.land,
                                  water=self.water)
        self.controls = MapControls(
            self.view, self.tools, self.getViewPort, editor=self.editor,
            height_at=lambda x, z: self.scene.height_at(x, z),
            on_change=self._map_moved, on_settle=self._settle)
        # The same scene from an angle: the map is what a line is drawn on, and
        # this is what the land is judged on. One window, two cameras.
        self.orbit = OrbitView(centre=self.view.centre)
        self.orbitPlatform = OrbitViewPlatform(self.orbit, self.getViewPort())
        self.orbitControls = OrbitControls(self.orbit, self.getViewPort,
                                           on_change=self._map_moved)
        #: Whether the window is showing the three-quarter view.
        self.perspective = False
        self._dirty_road = False
        #: Whether a stroke of the brush is waiting to be built into the scene.
        self._dirty_land = False
        #: Whether what is on screen is out of date with the project.
        self._stale = False
        self.sg = SceneGraph(children=[
            environment.horizon_background(),
            *ViewerContext.defaultLights(LIGHT_SCALE),
        ])
        self._rebuild()
        # Panels rather than HUD layers: a HUD takes no events, and a menu bar
        # and a tool palette are nothing but events. Neither is modal, so a
        # click that misses both reaches the map underneath.
        self.menus = MenuBar(menus=self._menus(), stack=self.overlays)
        self.overlays.push(self.menus)
        self.palette = ToolPalette(tools=self.tools, reserved=MENU_BAR_ROOM)
        self.overlays.push(self.palette)
        # The bar takes the top of the window and the palette the left, so the
        # read-outs start below one and beside the other.
        self.status = EditorStatus()
        #: The interface scale the read-outs were last given room for.
        self._reserved_at: float | None = None
        self._reserve_room()
        self.addHUDLayer(self.status)
        self._report()
        # Bound methods, not lambdas: handlers are held by weak reference, so a
        # callback with nothing else keeping it alive is collected the moment
        # this returns and the key is silently dead.
        self.addEventHandler('keypress', name='f', function=self._frame_all)
        self.addEventHandler('keypress', name='p', function=self._toggle_view)

    # -- what the project holds -------------------------------------------
    def _route(self) -> Any:
        route = self.project.route()
        if route is None:
            from glisteel_editor.project import Route
            route = Route(name='circuit')
            self.project.routes.append(route)
        return route

    def _route_changed(self) -> None:
        """The line moved: redraw it now, and rebuild the road when it settles."""
        self.project.touch()
        self._dirty_road = True
        self._rebuild()
        self._report()

    def _land_changed(self) -> None:
        """The ground moved under everything: redraw it when the pointer stops.

        A stroke of the brush changes the land, and everything derived from it
        -- where the road settles, what it has to be carried over, where the
        trees can stand. Redoing that per pointer-movement would make the
        gesture a slideshow, so the mesh under the brush is what moves while it
        is being dragged and the rest follows on settle.
        """
        self.project.touch()
        self._dirty_land = True
        self._report()

    def _settle(self) -> None:
        """Rebuild what a gesture implies, once the pointer has been let go."""
        if self._dirty_land:
            self._dirty_land = False
            self._dirty_road = False
            # The whole scene: the ground is what the road settles onto and
            # what the water runs down, so a stroke or a spring changes the
            # alignment and the rivers as well as the mesh.
            self.scene.reset()
            self._rebuild()
            self._report()
            return
        if not self._dirty_road:
            return
        self._dirty_road = False
        self.scene.route_changed()
        self._rebuild()
        self._report()

    def _rebuild(self) -> None:
        """Put the current scene in the window.

        Mid-drag this draws the line and its handles over whatever land and
        road were last built: the scene keeps them until it is told the line
        settled, and re-cutting the earthworks per mouse-move would make the
        drag a slideshow.
        """
        content = self.scene.build(
            self.view.metres_per_pixel(self.getViewPort()),
            self.editor.hovered, brush=self._brush())
        keep = [child for child in self.sg.children
                if not getattr(child, '_editorContent', False)]
        content._editorContent = True
        self.sg.children = keep + [content]
        self.triggerRedraw(1)

    def _viewpoint(self) -> str:
        """Where the camera is, for the read-out, or nothing on the map."""
        if not self.perspective:
            return ''
        return '%s away, %.0f deg up' % (
            _said(self.orbit.distance), self.orbit.pitch)

    def _tool_label(self) -> str:
        """What the pointer is doing, including anything holding it."""
        active = self.tools.active
        if active is None:
            return ''
        if active.name == 'route' and self.editor.snap:
            return '%s -- holding %g m' % (active.label,
                                           self.editor.snap_interval)
        return str(active.label)

    def _brush(self) -> tuple[tuple[float, float], float] | None:
        """Where a sculpting stroke would land, or None if none would.

        Only while the sculpt tool has the pointer: a ring left on the map
        under the route tool says the brush is about to do something it is not.
        """
        active = self.tools.active
        if active is None or active.name != 'sculpt' or self.land.at is None:
            return None
        return (self.land.at, self.land.radius)

    def _report(self) -> None:
        route = self.project.route()
        self.status.show(
            title=self.project.title(),
            points=len(route.points) if route else 0,
            length=route.length() if route else 0.0,
            scale=self.view.metres_per_pixel(self.getViewPort()),
            tool=self._tool_label(),
            structures=self.scene.structure_counts(),
            viewpoint=self._viewpoint())

    def ViewPort(self, width: int, height: int) -> None:
        """The window changed size: the map is measured against it.

        The scale, the pointer's reading and the size of a handle all come from
        the window's height, so a resize is not something the map can miss.
        """
        super().ViewPort(width, height)
        view = getattr(self, 'view', None)
        if view is None:
            return
        self.platform.setViewport(width, height or 1)
        self.orbitPlatform.setViewport(width, height or 1)
        self._report()
        # Not rebuilt here: a window being dragged to a new size sends a
        # stream of these, and re-meshing the landscape for each one would
        # stop the drag dead. The next frame picks it up.
        self._stale = True

    def _reserve_room(self) -> None:
        """Keep the read-outs out from under the bar and beside the palette.

        The palette's width is its labels, so it changes with the interface
        scale and with which tools the editor has; the read-outs are told in
        reference pixels and scale it themselves, which is why this is settled
        against the metrics the interface is actually drawn at rather than
        once at startup.
        """
        metrics = self.overlayMetrics()
        scale = float(getattr(metrics, 'scale', 0.0)) if metrics else 0.0
        self._reserved_at = scale
        self.status.reserved = (MENU_BAR_ROOM, 0.0, 0.0,
                                self.palette.room(metrics))

    def OnIdle(self, *args: Any) -> int:
        """Between frames: put right whatever an edit or a resize left stale."""
        metrics = self.overlayMetrics()
        if metrics is not None and float(metrics.scale) != self._reserved_at:
            self._reserve_room()
        if self._stale:
            self._stale = False
            self._rebuild()
            self._report()
        return 1

    # -- input -------------------------------------------------------------
    def ProcessEvent(self, event: Any) -> Any:
        if self.overlaySinks(event):
            return None
        if self._toolTook(event):
            self.triggerRedraw(1)
            return None
        return super().ProcessEvent(event)

    def _toolTook(self, event: Any) -> bool:
        kind = getattr(event, 'type', None)
        if kind == 'keyboard' and getattr(event, 'state', 0):
            if event.name == '<ctrl-z>':
                self._undo()
                return True
            if event.name == '<ctrl-y>':
                self._redo()
                return True
            if self.perspective:
                # The tools draw on the map; here the pointer is the camera's
                # and there is nothing for a key to reach.
                return False
            return self.controls.key(event.name, tuple(event.getModifiers()))
        if self.perspective:
            if kind == 'mousebutton':
                return bool(self.orbitControls.button(event))
            if kind == 'mousemove':
                return bool(self.orbitControls.moved(event))
            return False
        if kind == 'mousebutton':
            return bool(self.controls.button(event))
        if kind == 'mousemove':
            took = bool(self.controls.moved(event))
            if took and self._brush() is not None:
                # The brush's ring is part of the scene, so it follows the
                # pointer by the scene being put together again -- which is
                # cheap, because everything in it but the ring is kept.
                self._stale = True
            return took
        return False

    def _map_moved(self) -> None:
        """The map was panned or zoomed: the handles are a screen size."""
        self._stale = True
        self._report()

    def _tool_changed(self, tool: Any) -> None:
        """A different tool has the pointer: say so, and light its button."""
        self._report()
        self.triggerRedraw(1)

    def _frame_all(self, event: Any = None) -> None:
        minimum, maximum = self.project.bounds()
        if self.perspective:
            self.orbit.frame(minimum, maximum, self.getViewPort())
            self._map_moved()
            return
        self.controls.frame(minimum, maximum)

    # -- looking at it ------------------------------------------------------
    def _toggle_view(self, event: Any = None) -> None:
        """Swap between the map and the three-quarter view."""
        self._look_at_it(not self.perspective)

    def _look_at_it(self, perspective: bool) -> None:
        """Show the window's contents from an angle, or from straight above.

        The same scene either way -- nothing is rebuilt, so the swap is
        instant. The three-quarter view starts where the map was looking, so
        what was under the pointer is what is in front of the camera.
        """
        if bool(perspective) == self.perspective:
            return
        self.perspective = bool(perspective)
        if self.perspective:
            self.orbit.look_at(self.view.centre,
                               self.scene.height_at(*self.view.centre))
            # As much ground as the map was showing, so the swap does not
            # arrive somewhere else.
            half = self.view.span / 2.0
            self.orbit.frame((self.view.centre[0] - half,
                              self.view.centre[1] - half),
                             (self.view.centre[0] + half,
                              self.view.centre[1] + half),
                             self.getViewPort())
        else:
            # Where the camera was looking is where the map goes back to.
            self.view.centre = tuple(self.orbit.centre)
        self.platform = self.orbitPlatform if self.perspective else \
            self.mapPlatform
        self.platform.setViewport(*self.getViewPort())
        self._checkMenu('Look at it', self.perspective)
        self._stale = True
        self._report()

    def _checkMenu(self, text: str, checked: bool) -> None:
        """Keep a menu item's tick in step with a key that does the same."""
        for item in self.menus.allItems():
            if str(item.text) == text:
                item.checked = bool(checked)

    # -- the menus ----------------------------------------------------------
    def _menus(self) -> list:
        return [
            ('File', [
                MenuItem(text='New', on_activate=lambda w: self._new()),
                MenuItem(text='Open...', shortcut='<ctrl-o>',
                         on_activate=lambda w: self._open()),
                MenuItem(text='Save', shortcut='<ctrl-s>',
                         on_activate=lambda w: self._save()),
                Separator(),
                MenuItem(text='Bake a world', shortcut='<ctrl-b>',
                         on_activate=lambda w: self._bake()),
                MenuItem(text='Drive it', shortcut='<ctrl-d>',
                         on_activate=lambda w: self._drive()),
                Separator(),
                MenuItem(text='Quit', on_activate=lambda w: self._quit()),
            ]),
            ('Edit', [
                MenuItem(text='Undo', shortcut='<ctrl-z>',
                         on_activate=lambda w: self._undo()),
                MenuItem(text='Redo', shortcut='<ctrl-y>',
                         on_activate=lambda w: self._redo()),
            ]),
            ('Route', [
                MenuItem(text='Closed circuit', checkable=True,
                         checked=bool(self._route().closed),
                         on_activate=lambda w: self.editor.close_route(w.checked)),
                MenuItem(text='Clear', on_activate=lambda w: self._clear()),
            ]),
            ('Terrain', self._terrain_items()),
            ('View', [
                MenuItem(text='Look at it', shortcut='p', checkable=True,
                         checked=False,
                         on_activate=lambda w: self._look_at_it(
                             bool(w.checked))),
                MenuItem(text='Frame the landscape', shortcut='f',
                         on_activate=lambda w: self._frame_all()),
                MenuItem(text='Zoom in',
                         on_activate=lambda w: self.controls.zoom(1.0 / ZOOM_STEP)),
                MenuItem(text='Zoom out',
                         on_activate=lambda w: self.controls.zoom(ZOOM_STEP)),
                Separator(),
                MenuItem(text='Shaded relief', checkable=True,
                         checked=self.view_options['hillshade'],
                         on_activate=lambda w: self._show_land(
                             hillshade=bool(w.checked))),
                MenuItem(text='Contours', checkable=True,
                         checked=self.view_options['show_contours'],
                         on_activate=lambda w: self._show_land(
                             show_contours=bool(w.checked))),
                MenuItem(text='Contour interval',
                         submenu=self._interval_items()),
            ]),
        ]

    def _terrain_items(self) -> list:
        """The landscapes a track can be cut into, and which one it is on."""
        from OpenGLContext_editor.world.presets import PRESETS
        names = list(PRESETS)
        items = [MenuItem(text=PRESETS[name].label, checkable=True,
                          checked=(name == self._preset_name()))
                 for name in names]
        for item, name in zip(items, names, strict=True):
            item.on_activate = (lambda widget, name=name, items=items,
                                names=names: self._choose_terrain(name, items,
                                                                  names))
        return items

    def _preset_name(self) -> str | None:
        """Which preset the landscape is on, or None for something else."""
        return getattr(self.project.landscape.source.base, 'name', None)

    def _choose_terrain(self, name: str, items: list, names: list) -> None:
        """Cut the track into a different landscape.

        The line is kept: a designer choosing a landscape is choosing what the
        road runs over, not throwing the road away. Everything downstream of the
        ground -- the alignment, the earthworks, the structures -- is rebuilt,
        because all of it was an answer about the old one.
        """
        from OpenGLContext_editor.world.presets import PRESETS, PresetBase
        for item, offered in zip(items, names, strict=True):
            item.checked = (offered == name)
        self.project.landscape.source.base = PresetBase(name=name)
        self.project.touch()
        self.scene.reset()
        # How closely to describe the new land: a spacing that suits rolling
        # hills turns a mountain range into a hatch.
        self._choose_interval(self.scene.suggested_interval())
        self._say("Landscape: %s" % PRESETS[name].label)

    def _interval_items(self) -> list:
        """The contour spacings on offer, of which exactly one is in force."""
        chosen = self.view_options['contour_interval']
        items = [MenuItem(text='%g m' % metres, checkable=True,
                          checked=(metres == chosen))
                 for metres in CONTOUR_INTERVALS]
        for item, metres in zip(items, CONTOUR_INTERVALS, strict=True):
            item.on_activate = (lambda widget, metres=metres:
                                self._choose_interval(metres))
        #: Kept so a landscape that chooses its own spacing can tick it.
        self._interval_menu = items
        return items

    def _choose_interval(self, metres: float) -> None:
        """One spacing at a time: a menu of them is a choice, not a set."""
        for item, offered in zip(self._interval_menu, CONTOUR_INTERVALS,
                                 strict=True):
            item.checked = (offered == metres)
        self._show_land(contour_interval=metres)

    def _show_land(self, **options: Any) -> None:
        """Change how the land is read, and redraw it.

        The route's snap follows the contour spacing, so a designer holding the
        line to a height aims at a line that is actually on the map.
        """
        self.view_options.update(options)
        for name, value in options.items():
            setattr(self.scene, name, value)
        self.editor.snap_interval = self.view_options['contour_interval']
        self._rebuild()
        self._report()

    # -- what the menus do --------------------------------------------------
    def _new(self) -> None:
        self._replacing(self._really_new)

    def _really_new(self) -> None:
        self.project = new_project(extent=self.project.landscape.extent)
        self._adopt()

    def _open(self) -> None:
        path = self.config.project_path
        if not path or not os.path.exists(path):
            self._say("Open a track by naming it on the command line: "
                      "glisteel-editor mytrack.glisteel")
            return
        self._replacing(lambda: self._really_open(path))

    def _really_open(self, path: str) -> None:
        try:
            self.project = Project.open(path)
        except (OSError, ValueError) as error:
            self._say(str(error))
            return
        self._adopt()

    def _replacing(self, go: Any) -> None:
        """Do something that throws the current project away -- having asked.

        The same guard :meth:`_quit` uses, for the same reason: a project is the
        only copy of a designer's decisions, and New and Open replace it as
        completely as leaving does.
        """
        if not would_lose_work(self.project):
            go()
            return
        dialogs.confirm(
            "Replace without saving?",
            "%s has changes that are not in a file." % self.project.title(),
            on_answer=lambda yes: go() if yes else None,
            danger=True, context=self)

    def _adopt(self) -> None:
        """Point the editor at a different project."""
        self.scene = MapScene(self.project, **self.view_options)
        self.editor = RouteEditor(
            self._route(), on_change=self._route_changed,
            height_fn=lambda x, z: self.scene.world().natural()(x, z),
            snap=self.editor.snap,
            snap_interval=self.view_options['contour_interval'])
        self.land = LandEditor(self.project.landscape,
                               on_change=self._land_changed)
        self.water = WaterEditor(self.project.landscape,
                                 on_change=self._land_changed)
        self.tools = editor_tools(self.editor, self.view, self.getViewPort,
                                  on_change=self._map_moved,
                                  on_tool=self._tool_changed, land=self.land,
                                  water=self.water)
        self.controls.tools = self.tools
        self.controls.editor = self.editor
        self.palette.tools = self.tools
        self.palette.rebuild()
        self._reserve_room()
        self.overlays.invalidate()
        self._frame_all()

    def _save(self) -> None:
        path = self.project.path or self.config.project_path \
            or 'untitled.glisteel'
        self.project.save(path)
        self._say("Saved %s" % path)
        self._report()

    def _undo(self) -> None:
        """Take back the last thing the tool in force did.

        The tool rather than the editor, because the tools edit different
        things: one history over all of them would take back whichever change
        came last regardless of what the designer is working on.
        """
        if self.tools.undo():
            self._settle()
        else:
            self._say("Nothing to undo.")

    def _redo(self) -> None:
        if self.tools.redo():
            self._settle()
        else:
            self._say("Nothing to redo.")

    def _clear(self) -> None:
        route = self._route()
        if not route.points:
            return
        route.points.clear()
        self.editor.hovered = None
        self._route_changed()
        self._settle()

    def _bake(self) -> None:
        route = self.project.route()
        if route is None or not route.is_road():
            self._say("Draw a route first: click on the map to put points down.")
            return
        directory = self._bake_directory()
        self._say("Baking to %s ..." % directory)
        from OpenGLContext_editor.bake.driver import bake_world
        from OpenGLContext_editor.world.procedural import CREDITS
        world = self.project.world()
        result = bake_world(world.layers(), directory, depth=4,
                            credits=list(CREDITS))
        self.config.baked = result.tileset
        self._say("Baked %d tiles to %s" % (result.tiles, result.tileset))

    def _bake_directory(self) -> str:
        return bake_directory(self.project)

    def _drive(self) -> None:
        tileset = self.config.baked or os.path.join(self._bake_directory(),
                                                    'tileset.json')
        if not os.path.exists(tileset):
            self._say("Bake a world first (File -> Bake a world).")
            return
        import shutil
        import subprocess
        command = shutil.which('glisteel')
        if command is None:
            self._say("glisteel is not installed: pip install glisteel")
            return
        subprocess.Popen([command, tileset])           # noqa: S603
        self._say("Driving %s" % tileset)

    def _quit(self) -> None:
        if would_lose_work(self.project):
            dialogs.confirm(
                "Leave without saving?",
                "%s has changes that are not in a file." % self.project.title(),
                on_answer=lambda yes: self._leave() if yes else None,
                danger=True, context=self)
            return
        self._leave()

    def _leave(self) -> None:
        self.OnQuit()

    def _say(self, message: str) -> None:
        log.info("%s", message)
        self.status.message = message
        self.triggerRedraw(1)


def would_lose_work(project: Any) -> bool:
    """Whether replacing this project would throw away something unsaved.

    Asked before New, Open and Quit alike, so the three cannot come to disagree
    about it: each of them replaces a designer's work as completely as the
    others, and the project file is the only copy there is.
    """
    return bool(project is not None and project.dirty)


def bake_directory(project: Any) -> str:
    """Where a bake of this project goes: beside its file, or beside the editor.

    Named after the project rather than after the run, so baking twice replaces
    a world rather than collecting them.
    """
    stem = (os.path.splitext(project.path)[0] if project.path
            else os.path.join(os.getcwd(), project.name or 'track'))
    return stem + BAKE_SUFFIX


def _preset_names() -> list[str]:
    from OpenGLContext_editor.world.presets import PRESETS
    return list(PRESETS)


def terrain_base(options: Any) -> Any:
    """Where a new project's ground comes from, as the command line asked.

    An elevation file wins over a named preset, since a designer who supplied
    one is asking for that ground and nothing else; with neither, the project
    gets the shipped landscape.
    """
    if getattr(options, 'dem', None):
        from OpenGLContext_editor.world.dem import DEMBase
        if not options.centre:
            raise SystemExit(
                "--dem needs --centre LAT,LONG to say where on the Earth the "
                "middle of the map is")
        latitude, longitude = (float(part)
                               for part in str(options.centre).split(','))
        return DEMBase(path=options.dem, centre=(latitude, longitude),
                       datum=float(getattr(options, 'datum', 0.0) or 0.0))
    if getattr(options, 'terrain', None):
        from OpenGLContext_editor.world.presets import PRESETS, PresetBase
        if options.terrain not in PRESETS:
            raise SystemExit(
                "there is no landscape called %r; the ones there are: %s"
                % (options.terrain, ', '.join(PRESETS)))
        return PresetBase(name=options.terrain)
    return None


def _said(metres: float) -> str:
    """A distance as a person would say it."""
    if metres >= 1000.0:
        return '%.2f km' % (metres / 1000.0)
    return '%.0f m' % metres


def _at(x: float, y: float, z: float) -> Any:
    import numpy as np
    return np.array([float(x), float(y), float(z)], dtype='d')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='glisteel-editor',
        description="Draw a circuit on a landscape and bake a world to drive.")
    parser.add_argument('project', nargs='?', default=None,
                        help="a .glisteel track file to open, or nothing for a "
                             "fresh landscape")
    parser.add_argument('--extent', type=float, default=2048.0,
                        help="how many metres across a new landscape is")
    parser.add_argument('--seed', type=int, default=11,
                        help="which trees and rocks a new project gets")
    parser.add_argument('--terrain', default=None,
                        help="a landscape to start from: %s"
                             % ', '.join(_preset_names()))
    parser.add_argument('--dem', default=None,
                        help="an SRTM .hgt elevation file to cut the track "
                             "into, instead of a generated landscape")
    parser.add_argument('--centre', default=None,
                        help="where on the Earth the middle of the map is, as "
                             "LAT,LONG; needed with --dem")
    parser.add_argument('--datum', type=float, default=0.0,
                        help="how many metres above the waterline the middle "
                             "of an imported landscape sits")
    parser.add_argument('--size', default='1280x800',
                        help="window size, WIDTHxHEIGHT")
    return parser


def main(argv: list[str] | None = None) -> int:   # pragma: no cover - needs a window
    logging.basicConfig(level=logging.INFO)
    options = build_parser().parse_args(argv)
    if options.project and os.path.exists(options.project):
        project = Project.open(options.project)
    else:
        project = new_project(extent=options.extent, seed=options.seed,
                              base=terrain_base(options))
        if options.project:
            project.path = options.project
    options.project_path = options.project
    options.project = project
    options.baked = None
    width, height = (int(part) for part in options.size.lower().split('x'))

    class Editor(EditorContext):
        config = options

    Editor.ContextMainLoop(size=(width, height))
    return 0


if __name__ == '__main__':                           # pragma: no cover
    sys.exit(main())
