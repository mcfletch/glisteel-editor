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
from OpenGLContext.edit.tools import ToolManager  # noqa: E402
from OpenGLContext.scenegraph.scenegraph import SceneGraph  # noqa: E402
from OpenGLContext.ui import dialogs  # noqa: E402
from OpenGLContext.ui.menu import MenuBar, MenuItem  # noqa: E402
from OpenGLContext.ui.overlay import OverlayMixin  # noqa: E402
from OpenGLContext.ui.widgets import Separator  # noqa: E402
from OpenGLContext.viewer import environment  # noqa: E402
from OpenGLContext.viewer.sceneviewer import ViewerContext  # noqa: E402

from glisteel_editor.controls import ZOOM_STEP, MapControls  # noqa: E402
from glisteel_editor.editing import RouteEditor, RouteTool  # noqa: E402
from glisteel_editor.project import Project, new_project  # noqa: E402
from glisteel_editor.scene import MapScene  # noqa: E402
from glisteel_editor.status import EditorStatus  # noqa: E402

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


class EditorContext(OverlayMixin, BaseContext):    # pragma: no cover - needs a window
    """The editor's window: a map, a menu bar, and the tools in between."""

    config: Any = None

    def OnInit(self) -> None:
        self.project = self.config.project
        self.scene = MapScene(self.project)
        self.view = MapView(centre=(0.0, 0.0),
                            span=self.project.landscape.extent)
        # The platform the context made for itself is a perspective camera;
        # this one reads the map. It has to be told the window's size, because
        # the context told the one it is replacing and will not do it again
        # until the window is resized.
        self.platform = MapViewPlatform(self.view, self.getViewPort())
        self.platform.setViewport(*self.getViewPort())
        self.editor = RouteEditor(self._route(), on_change=self._route_changed)
        self.tools = ToolManager([RouteTool(editor=self.editor)])
        self.controls = MapControls(
            self.view, self.tools, self.getViewPort, editor=self.editor,
            height_at=lambda x, z: self.scene.height_at(x, z),
            on_change=self._map_moved, on_settle=self._settle)
        self._dirty_road = False
        #: Whether what is on screen is out of date with the project.
        self._stale = False
        self.sg = SceneGraph(children=[
            environment.horizon_background(),
            *ViewerContext.defaultLights(LIGHT_SCALE),
        ])
        self._rebuild()
        # The bar takes the top of the window, so the read-outs start below it.
        self.status = EditorStatus(reserved=(MENU_BAR_ROOM, 0.0, 0.0, 0.0))
        self.addHUDLayer(self.status)
        # At the bottom of the overlay stack rather than a HUD layer: a HUD
        # takes no events, and a menu bar is nothing but events. It is not
        # modal, so a click that misses it reaches the map underneath.
        self.menus = MenuBar(menus=self._menus(), stack=self.overlays)
        self.overlays.push(self.menus)
        self._report()
        self.addEventHandler('keypress', name='f', function=self._frame_all)

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
        self._rebuild(road=False)
        self._report()

    def _settle(self) -> None:
        """Rebuild what the line implies, once the pointer has been let go."""
        if not self._dirty_road:
            return
        self._dirty_road = False
        self.scene.route_changed()
        self._rebuild()
        self._report()

    def _rebuild(self, road: bool = True) -> None:
        """Put the current scene in the window."""
        if road:
            content = self.scene.build(self.view.metres_per_pixel(self.getViewPort()),
                                       self.editor.hovered)
        else:
            # Mid-drag: the line and its handles, over whatever land and road
            # were last built. Re-cutting the earthworks per mouse-move would
            # make the drag a slideshow.
            content = self.scene.build(self.view.metres_per_pixel(self.getViewPort()),
                                       self.editor.hovered)
        keep = [child for child in self.sg.children
                if not getattr(child, '_editorContent', False)]
        content._editorContent = True
        self.sg.children = keep + [content]
        self.triggerRedraw(1)

    def _report(self) -> None:
        route = self.project.route()
        self.status.show(
            title=self.project.title(),
            points=len(route.points) if route else 0,
            length=route.length() if route else 0.0,
            scale=self.view.metres_per_pixel(self.getViewPort()),
            tool=self.tools.active.label if self.tools.active else '')

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
        self._report()
        # Not rebuilt here: a window being dragged to a new size sends a
        # stream of these, and re-meshing the landscape for each one would
        # stop the drag dead. The next frame picks it up.
        self._stale = True

    def OnIdle(self, *args: Any) -> int:
        """Between frames: put right whatever an edit or a resize left stale."""
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
            return self.controls.key(event.name, tuple(event.getModifiers()))
        if kind == 'mousebutton':
            return bool(self.controls.button(event))
        if kind == 'mousemove':
            return bool(self.controls.moved(event))
        return False

    def _map_moved(self) -> None:
        """The map was panned or zoomed: the handles are a screen size."""
        self._stale = True
        self._report()

    def _frame_all(self, event: Any = None) -> None:
        minimum, maximum = self.project.bounds()
        self.controls.frame(minimum, maximum)

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
            ('Route', [
                MenuItem(text='Closed circuit', checkable=True,
                         checked=bool(self._route().closed),
                         on_activate=lambda w: self.editor.close_route(w.checked)),
                MenuItem(text='Clear', on_activate=lambda w: self._clear()),
            ]),
            ('View', [
                MenuItem(text='Frame the landscape', shortcut='f',
                         on_activate=lambda w: self._frame_all()),
                MenuItem(text='Zoom in',
                         on_activate=lambda w: self.controls.zoom(1.0 / ZOOM_STEP)),
                MenuItem(text='Zoom out',
                         on_activate=lambda w: self.controls.zoom(ZOOM_STEP)),
            ]),
        ]

    # -- what the menus do --------------------------------------------------
    def _new(self) -> None:
        self.project = new_project(extent=self.project.landscape.extent)
        self._adopt()

    def _open(self) -> None:
        path = self.config.project_path
        if not path or not os.path.exists(path):
            self._say("Open a track by naming it on the command line: "
                      "glisteel-editor mytrack.glisteel")
            return
        self.project = Project.open(path)
        self._adopt()

    def _adopt(self) -> None:
        """Point the editor at a different project."""
        self.scene = MapScene(self.project)
        self.editor = RouteEditor(self._route(), on_change=self._route_changed)
        self.tools = ToolManager([RouteTool(editor=self.editor)])
        self.controls.tools = self.tools
        self.controls.editor = self.editor
        self._frame_all()

    def _save(self) -> None:
        path = self.project.path or self.config.project_path \
            or 'untitled.glisteel'
        self.project.save(path)
        self._say("Saved %s" % path)
        self._report()

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
        stem = (os.path.splitext(self.project.path)[0] if self.project.path
                else os.path.join(os.getcwd(), self.project.name or 'track'))
        return stem + BAKE_SUFFIX

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
        if self.project.dirty:
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
                        help="which landscape a new project gets")
    parser.add_argument('--size', default='1280x800',
                        help="window size, WIDTHxHEIGHT")
    return parser


def main(argv: list[str] | None = None) -> int:   # pragma: no cover - needs a window
    logging.basicConfig(level=logging.INFO)
    options = build_parser().parse_args(argv)
    if options.project and os.path.exists(options.project):
        project = Project.open(options.project)
    else:
        project = new_project(extent=options.extent, seed=options.seed)
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
