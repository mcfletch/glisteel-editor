# glisteel-editor remediation plan

Status: **Complete** — 2026-08-19. A through K have landed; see the record
under each phase, and *What is still open* at the foot.

A designer sat down with the track editor and wrote up what stops them getting a
track built. This plan takes that list, decides where each fix belongs, and puts
the items in an order where the foundations land before the tools that stand on
them.

## The list, verbatim

0. *(added after the list was worked through)* No way to see the land in three
   dimensions while working: the editor is a map, and the shape of what a
   sculpting stroke made is read from shading and contours rather than looked at.
1. Menus are glacially slow — several seconds to open after the click.
2. No way to choose the area to use as the heightmap; want sample DEM setups for
   dramatic mountains, lakes, hills, canyons, and a way to give a lat/long centre.
3. Nothing indicates topology — it is a flat map, so you cannot see what the
   final product will look like.
4. No way to paint a river, or better, cause water to well up at a point and flow
   downhill from there.
5. No way to edit the land — raise or lower height in an area, preferably with
   fractal detail so it stays natural.
6. No way to set the start/end of the track.
7. No way to snap the track to iso-height lines (or close to it).
8. No support for switchbacks — when a road really does need to climb a mountain.
9. Wants a toolbox on the left of the HUD to trigger tools, with the menus left
   for whole-map operations.

## Where each fix belongs

The editor is deliberately thin: it draws a plan view, routes the pointer to a
tool, and hands a project's decisions to the world generator. The engine-first
rule in [../../CLAUDE.md](../../CLAUDE.md) applies with full force here — a
capability a *game* editor built on this toolkit would also want goes into the
engine or the world generator, and the editor calls it. Almost everything on
this list is that kind of capability.

| # | Item | Home | New surface |
|---|------|------|-------------|
| 1 | Menu latency | **OpenGLContext** `ui/` (overlay/menu/draw) | none — a defect to find and fix |
| 2 | Heightmap source / DEM presets / lat-long | **openglcontext-editor** `world/` + editor `project.py` | a height-source abstraction and a preset library |
| 3 | Topology / relief | **OpenGLContext** map render + editor `scene.py` | shaded relief + contour overlay for a plan view |
| 4 | Hydrology (rivers) | **openglcontext-editor** `world/` | downhill flow from a source, a carved channel, a water surface |
| 5 | Land sculpting | **openglcontext-editor** `world/` (editable height) + editor tool | an edit layer on the height field |
| 6 | Start / finish | **openglcontext-editor** `world/route.py` + editor `editing.py` | route endpoints and a grid marker |
| 7 | Iso-height snap | editor `editing.py` (uses engine height field) | a snap on point placement and drag |
| 8 | Switchbacks | **openglcontext-editor** `world/route.py` | grade-climbing plan operation |
| 9 | Tool palette | **OpenGLContext** `ui/` + `edit/` + editor wiring | a HUD tool palette bound to `ToolManager` |
| 0 | Seeing it in three dimensions | **OpenGLContext** `edit/` + editor wiring | an orbiting camera over the same scene |

Nothing on this list is fixed in the editor alone. Items 6, 7 and 9 have their
*wiring* in the editor; their reusable machinery is in the engine or the world
generator.

## Shape of the work

Three of these are foundations that the rest stand on, and they come first:

- **A. Menu latency (item 1).** Usability blocker; independent of everything
  else; measure-first.
- **B. Tool palette and a tool-mode spine (item 9).** Every new authoring verb —
  sculpt, paint water, place start/finish — is a `ToolMode`. Build the palette
  and the mode-switching before the tools that populate it, or each tool grows
  its own ad-hoc key binding and the interaction model fractures.
- **C. Editable height source (part of items 2 and 5).** Sculpting, hydrology,
  DEM import and the preset library all need the landscape's height to stop being
  a single pure function and become *a base source plus an ordered stack of
  edits*, serialised in the project. This is the largest data-model change and it
  gates the most items.

Then the map-legibility fix (D, item 3), the terrain-authoring tools (E–G, items
2/5/4), and the route-authoring work (H–J, items 6/7/8).

Every phase carries its own tests (Red/Green, headless — the editor suite already
runs without a window) and its own documentation, per the workspace rules. A
phase is not done until `README.md` (and the relevant engine/world docs) describe
the new verb, its units and its limits.

---

## A. Menu latency — find it, then fix it in the engine (item 1)

**Symptom.** Several seconds between clicking a menu title and the list appearing.

**What it is not.** Menu layout is cheap: `FontMetrics.text_width` is
`len(text) * char_width`, and a menu is a handful of short rows. The seconds are
not spent measuring text.

**Measure first.** The engine ships the tool for exactly this — do not guess:

```bash
OPENGLCONTEXT_STALL_TRACE=/tmp/menu-stalls.jsonl \
  /workspaces/OpenGL-dev/.venv/bin/glisteel-editor some-track.glisteel
# open a menu a few times, quit
/workspaces/OpenGL-dev/.venv/bin/python -m OpenGLContext.stalltrace /tmp/menu-stalls.jsonl
```

The trace samples the main-thread stack *while the stall is happening* and leads
with a per-function tally, so it names the hot call rather than leaving it to
inference. `OPENGLCONTEXT_STALL_MS=40` with `looptrace` splits the iteration into
`draw` / `idle` / `wait`, which distinguishes a CPU stall from a GPU-bound redraw.

**Candidates the trace will decide between.**

- *A redraw of the full scene per overlay frame.* Opening a menu pushes an
  overlay and triggers redraws; each redraw draws the 129×129 PBR terrain mesh,
  the road and the tarmac texture. On a modest GPU (this workspace's reference is
  an Intel UHD 630 — see the forest-demo perf notes) that draw can be the cost,
  and it would show as `draw`/GPU time, not a CPU stall. If so the fix is to stop
  redrawing the world to animate an overlay: the plan view is static while a menu
  is open, so composite the menu over the **last world frame** rather than
  re-rendering it. That belongs in the engine's overlay path, and it helps every
  application that puts an overlay over an expensive scene.
- *Per-open relayout/relink of the whole overlay stack*, including the HUD
  read-outs and skin scaling. If `draw` is small and the time is in layout, fix
  the redundant work in `ui/panel.py` / `ui/overlay.py`.
- *First-use glyph-atlas or shader build* stalling the first open only. If it is
  one-time, warm it at startup.

**Deliverable.** A named cause backed by a trace excerpt in this plan, a fix in
the engine `ui/` (or `passes/` if it is the redraw), and a regression guard —
either a unit test on the overlay path or a `looptrace` assertion that opening a
menu does not re-render the scene. Engine docs (`docs/overlayui.html`) updated if
the overlay-compositing contract changes.

### What it turned out to be — **Done**, 2026-08-19

**Neither candidate.** A plan-view frame is cheap: measured over 70 frames at
1280×800 with a five-point circuit, a full redraw — terrain, road, structures,
markers, HUD and menu bar — has a **median of 2.9 ms**, and 3.2 ms with a menu
open. Layout is cheap too: opening the File menu and drawing the frame that
shows it costs **3.3 ms**, first open included. Nothing in the drawing or the
laying out is worth seconds.

**The click was not being delivered.** Driving the shipped editor's own loop and
injecting a click on a menu title the way a windowing backend does
(`addPickEvent` + `triggerPick`):

```
clicked File at (76, 782)
menu never appeared within 20 s (1959 loop iterations)
```

A pick is read back **asynchronously**: the samples are read into a fenced pixel
buffer during one render (`passes/asyncpick.py`, `submitAsyncPicks`) and the
event is dispatched by `drainAsyncPicks` during a **later** one. `drainAsyncPicks`
only runs inside a render, and the editor — like any application that draws only
when something changed — has nothing to change while the pick is in flight. So
nothing asked for the frame the readback needed, and the click sat in the queue
until some unrelated event happened to ask for one. Instrumented over the six
seconds after the click: `submit 1, drain 1, resolve 0`. That is the "several
seconds": the menu opens when the pointer next moves.

**Fix (engine, `passes/asyncpick.py`).** A batch in flight asks the context for
the frame it will be delivered on, and stops as soon as the queue empties, so a
loop with no picks outstanding still goes quiet. Same measurement afterwards:

```
menu appeared after 10 ms, 2 loop iterations
```

**A second defect, found on the way.** With a **three-point** route the editor
died on its first frame: `GL_INVALID_OPERATION` from `glUniformMatrix4fv` in the
shadow depth pass. A caster binds whatever program it draws through — an
`IndexedLineSet` draws through the unlit program and leaves the lit one bound —
and `_renderDepth` then uploaded the next caster's light-space modelview against
the *depth* program's uniform location into whichever program was actually
bound. Where a location happened to exist it wrote into the wrong uniform
silently; where it did not, it raised. Fixed in
`passes/shadowmixin.py`: the depth pass binds its own program per caster and per
instanced group rather than trusting the caster before it.

**Guards.**

- `openglcontext/tests/unit/test_asyncpick_delivery.py` — a batch still in
  flight asks for a frame; a resolved one and an empty queue ask for nothing.
- `openglcontext/tests/unit/test_pick_delivery_interactive.py` — end to end
  through the real pick path: a click reaches the handler of an application
  whose `OnIdle` never asks to draw.
- `openglcontext/tests/unit/test_shadow_depth_program_gl.py` — the depth pass
  uploads into the program it names.

**Also landed.** `EventInjectionMixin` events take `"pick": true`, which queues
the event for the selection pass instead of handing it straight to its manager
— the path a real click takes, and the only way an interactive test can prove
what a click does to an application.

**Docs.** `openglcontext/docs/overlayui.html` (layered input routing, below).

---

## B. Tool palette and the tool-mode spine (item 9)

**Goal.** A vertical palette down the left of the HUD, one button per tool, the
active tool lit. Clicking a button makes that tool the one the pointer drives.
The menus keep the whole-map operations (New, Open, Save, Bake, Drive, and the
terrain-source and view commands), and lose nothing they do today.

**Where.** The `ToolManager` already exists in
[../../openglcontext/OpenGLContext/edit/tools.py](../../openglcontext/OpenGLContext/edit/tools.py)
and already holds a list of `ToolMode`s; the editor builds one with a single
`RouteTool`. Two pieces are missing and both belong in the engine, because any
editor built on the toolkit wants them:

1. A **`ToolPalette` HUD widget** in `OpenGLContext/ui/` — a column of toggle
   buttons anchored left, reading its entries from a `ToolManager` and calling
   into it to switch the active mode. It reuses the existing HUD widgets and skin
   (`ui/hudwidgets.py`, `ui/widgets.py`); it is a sibling of `MenuBar`.
2. **Active-mode switching** on `ToolManager` (select by name, expose the active
   mode and an `on_change` hook) if it is not already there — check
   `edit/tools.py` before adding.

**Editor wiring.** `app.py` builds the palette next to the status HUD, registers
the tools it has, and reserves the left strip the way it already reserves the top
for the menu bar (`MENU_BAR_ROOM`, `EditorStatus(reserved=...)`). The status
read-out already shows the active tool's label (`status.py`), so the palette and
the read-out agree for free.

**Day-one tools.** *Draw route* (the current `RouteTool`) and *Pan/zoom* (the
map-move behaviour, made an explicit mode so a designer can put the pointer into
"move the map" without the route tool second-guessing it). Sculpt, Paint water
and Set start/finish slot in as later phases add them.

**Tests.** The palette and mode-switching are plain objects driven by synthetic
events — headless, no window. Assert that selecting a tool changes
`ToolManager.active`, that the palette reflects an external mode change, and that
a click on a palette button does not also fall through to the map.

**Docs.** `README.md` gains a "Tools" section; the engine's editing overview
(`openglcontext/docs/editing.html`) documents `ToolPalette`.

### What landed — **Done**, 2026-08-19

`ToolManager` already had `select`/`active`/`on_change`, so what was missing was
the widget, a pan mode, and one thing neither of them could work without.

- **`OpenGLContext/ui/toolpalette.py`** — `ToolPalette` (a non-modal panel
  anchored to either side, with a `reserved` top offset) and `ToolButton`. A
  button reads the manager rather than keeping a copy, so a tool chosen
  elsewhere lights the right button and a manager that refuses the change
  mid-gesture leaves the strip telling the truth. A press anywhere on the strip
  is the strip's, so a click that missed a button by two pixels does not put a
  point down on the map underneath. `room(metrics)` answers how much width to
  keep clear, in the reference pixels a `HUDLayer.reserved` is measured in.
- **`OpenGLContext/ui/overlay.py`** — an event is offered to the panels topmost
  first, down to and including the first modal one, and stops at whichever takes
  it; the pointer's *position* goes to every layer, because hover is not
  something one layer takes from another. Without this an application could have
  a menu bar **or** a palette but not both: only the top panel heard anything.
- **`OpenGLContext/edit/maptools.py`** — `PanTool`, moving the map as a mode of
  its own. The drag is measured from where the pointer last was, since the map
  moves underneath it.
- **Editor** — `editing.editor_tools()` builds the manager (drawing first, then
  pan) as a plain function a test can call; `app.py` pushes the palette beside
  the menu bar and keeps the read-outs clear of it as the interface scale
  changes.

**Guards.** `openglcontext/tests/unit/test_ui_toolpalette.py`,
`tests/unit/test_edit_maptools.py`, the two new cases in
`tests/unit/test_ui_overlay.py`, and `glisteel-editor/tests/test_tools.py` —
which asserts the thing the designer asked for: with **Pan/zoom** chosen, a
left click on the map moves it instead of gaining a point.

---

## C. Editable height source — the terrain data model (foundation for 2, 4, 5)

Today `Landscape` is `(extent, seed, resolution, tree_density)` and the height is
one pure function, `terrain_height`, scaled by relief in `ProceduralWorld`. That
cannot represent an imported DEM, a sculpted hill or a carved riverbed. It has to
become a **height source**: a base plus an ordered, serialisable stack of edits.

**Model (in openglcontext-editor `world/`).**

```
HeightSource
  base:  ProceduralBase(seed, relief) | DEMBase(dataset, centre, extent) | PresetBase(name)
  edits: [ SculptStroke(...), Channel(...), ... ]   # ordered, each a bounded delta
  height_fn() -> vectorised f(x, z) -> elevation     # base then edits applied in order
```

Every edit is a **bounded, vectorised delta** over `(x, z)` so the existing
`terrain_patch` / `height_fn` consumers do not change shape — they still call one
callable. The base stays a pure function; the edits are data.

**Project file (editor `project.py`).** `Landscape` grows a `source` block and a
`terrain` version bump (`Project.VERSION` → 2; the existing refuse-newer guard
already protects older readers). A v1 file with no `source` reads as today's
procedural base, so old tracks keep opening. The edit stack is JSON a designer can
read, consistent with the "a project is the decisions, not the world" principle in
`project.py`.

**Performance.** The height function is called across whole tiles during bake and
across the 129² editor mesh on every settle. Edits must evaluate vectorised and be
spatially bounded (each carries its affected rectangle; outside it, it contributes
nothing and is skipped). Sculpting must not turn the height function into a Python
loop over strokes per sample — this is the headroom the engine-first rule demands.

**Tests.** Height-source composition is pure arithmetic: assert base-only equals
`terrain_height * relief`, that a stroke raises its region and leaves the rest
untouched, that edits compose in order, and that round-tripping through JSON
reproduces the field. No GL needed.

**Docs.** `README.md` "What a project is" gains the `source`/edit-stack shape;
openglcontext-editor documents `HeightSource`.

This phase lands the model with the **procedural base only** and an empty,
serialisable edit stack. DEM bases (E) and the concrete edit kinds (F sculpt, G
channel) build on it.

### What landed — **Done**, 2026-08-19

`OpenGLContext_editor.world.height`:

- `HeightBase` / `HeightEdit`, both abstract, both serialisable, with
  `register_base` / `register_edit` declaring the kinds a file may name. A kind
  this version does not know is **refused rather than dropped**.
- `ProceduralBase(relief)` — the shipped landscape, and the only base this phase
  ships. `procedural.RELIEF` now *is* `height.DEFAULT_RELIEF`, so the two cannot
  drift.
- `HeightSource(base, edits).height_fn()` — one ordinary callable over
  `(x, z)`. Each edit declares the rectangle it can reach and is asked only
  about samples inside it, all at once; outside it, one comparison. The base's
  answer is copied before the first edit writes into it, so a base that keeps
  its array is not written through.
- `ProceduralWorld(source=...)` takes one; `natural()` is now
  `height_source().height_fn()`, and a world given no source is the shipped
  landscape at its own `relief` — the same thing said the short way.
- `Landscape.source` in the editor, `Project.VERSION` → 2. A version-1 file has
  no `source` block and reads as the landscape it always was.

**Guards.** `openglcontext-editor/tests/test_world_height.py` (base, edit
composition, bounding, JSON round trip, and the world built on one) and the
`TestTheHeightSource` cases in `glisteel-editor/tests/test_project.py`.

**Docs.** openglcontext-editor `README.md` ("Where the ground comes from") and
glisteel-editor `README.md` ("What a project is").

---

## D. Topology — shaded relief and contours (item 3)

**Symptom.** The plan view is lit bright and from straight overhead
(`LIGHT_SCALE = 400`, high light, `scene.py`), which is deliberate for reading a
line but flattens the land — a designer cannot see a ridge from a valley.

**Fix.** Give the plan view a relief read-out that does not fight the line:

1. **Hillshade.** Shade the ground by its slope relative to a fixed low "sun"
   (a standard cartographic hillshade computed from the height field's gradient),
   instead of the flat overhead PBR lighting. The terrain mesh already has
   normals from `terrain_patch`; a hillshade is a function of that normal and a
   light azimuth/altitude. This is a **map-rendering capability**, so the shading
   belongs in the engine's plan-view/map path (`OpenGLContext/edit/`), with
   `scene.py` selecting it — not hand-rolled in the editor.
2. **Contours.** Iso-height lines at a chosen interval, drawn over the ground and
   labelled at the scale a whole circuit is read at. Contour extraction from a
   sampled height field (marching squares) is reusable — it belongs in
   openglcontext-editor beside the terrain, and item 7's snap consumes the same
   contours. `scene.py` mounts them as another overlay child alongside the guide
   line and the structure marks.

A **View-menu toggle** for each (hillshade, contours, contour interval), so a
designer can turn them off when reading the line alone.

**Tests.** Contour extraction is pure: assert a known height field yields closed
loops at the right elevations and the right count. Hillshade is a shader/normal
computation — cover the CPU-side normal-to-shade math and add a plan-view
reference image if one fits the engine's visual-regression suite.

**Docs.** `README.md` "Drawing"/"Limits"; engine editing docs for the relief and
contour options.

### What landed — **Done**, 2026-08-19

- **`OpenGLContext/edit/relief.py`** — `light_vector`, `hillshade`, `steepen`
  and `shade_colors`. The sun is north-west at 45°, the cartographic
  convention, because relief lit from east of north reads as hollows. The
  shading goes into the vertex colours and the ground is drawn **unlit**, so the
  plan view needs no lights and builds no shadow maps.
- **Vertical exaggeration, ×4 by default.** Country a road can be built through
  is gentle, and shading it honestly leaves a flat green sheet; every printed
  relief map of lowland does the same. It is in the shading only.
- **`OpenGLContext_editor.world.contours`** — `contour_levels`, `contours` over
  a sampled grid and `contours_of` over a height function. Marching squares,
  with the saddle resolved against the cell's own average and the segments
  chained into polylines; a line that returns to its start is a closed loop.
- **Editor** — `MapScene.hillshade`, `show_contours` and `contour_interval`,
  each rebuilding only what it changes, with a View menu that toggles the first
  two and offers 10/25/50/100 m for the third. Contours are of the *landscape*,
  not of the baked ground, so earthworks do not redraw the map a grade is
  measured against; they are lifted onto the drawn ground rather than left at
  their own elevation, because the ground mesh is straight lines between samples
  metres apart and would bury them.

**Three engine defects found by looking at the result.** The map was drawn and
read, which is how they surfaced:

1. **A colourless `IndexedLineSet` or `PointSet` drew nothing at all.** The
   unlit program reads the vertex position at attribute 2 and the line/point
   programs read it at 0; both nodes bound it at 0 whichever program they had
   chosen, so every vertex of a colourless line landed at the origin — silently,
   with no GL error. The editor's own route line had been invisible.
   `VRML97ShaderProgram.position_location(program)` now answers which, and both
   nodes ask.
2. **A colourless line or point cloud ignored its material.** It drew white
   whatever the `Shape`'s appearance said. `Shape` now publishes
   `appearance_solid_color(appearance)` on the mode and both nodes take it, so a
   yellow material draws a yellow line.
3. **`hasVertexColor` was sticky.** It is one uniform for the whole pass and
   only `PBRMesh` maintained it, so any other geometry drawn after a
   vertex-coloured mesh was modulated by a colour attribute it does not supply —
   which reads as **black**. The editor's control-point handles came out black
   about half the time, depending on the order the pass happened to draw in.
   `Shape` now answers it for every shape.

**Guards.** `tests/unit/test_edit_relief.py`,
`tests/unit/test_unlit_geometry_gl.py` (both nodes drawn, in the right place and
the right colour), `tests/unit/test_shape_vertex_color.py`,
`openglcontext-editor/tests/test_world_contours.py`, and the
`TestReadingTheRelief` / `TestTheContours` cases in
`glisteel-editor/tests/test_scene.py`.

**Docs.** `openglcontext/docs/editing.html` ("Reading relief off a plan view"),
openglcontext-editor `README.md` ("Read the land off it"), glisteel-editor
`README.md` ("Reading the land" and "Limits").

---

## E. Heightmap source: DEM presets and lat/long centre (item 2)

Builds on **C**. Adds concrete bases behind `HeightSource`:

- **Preset library.** A named set of dramatic procedural bases — *mountains*,
  *lakes*, *rolling hills*, *canyon* — each a tuned parameterisation of the
  procedural terrain (relief, ridged/billow noise, water level). These live in
  openglcontext-editor as data, so a game editor gets the same starting points.
  The editor exposes them as a **Terrain menu** ("New from preset…") and, once the
  tool palette exists, the New/terrain dialog.
- **Real DEM import.** A `DEMBase` that samples a real elevation dataset for a
  region. Scope in two steps: (i) load a DEM the user supplies as a file, sampled
  under a chosen `extent`; (ii) fetch by **lat/long centre** from an open
  elevation source. DEM formats (GeoTIFF, SRTM `.hgt`) have **open public specs**
  (USGS/NASA), so no clean-room constraint applies to the format itself; if any
  candidate *reader library* is copyleft, [../../CLEAN-ROOM.md](../../CLEAN-ROOM.md)
  governs and we prefer a permissively-licensed reader or the raw byte spec.
  A network fetch is optional and off by default — the editor must stay usable
  with no network.
- **Lat/long centre** is a field on `DEMBase`, recorded in the project so a
  reopened track resolves to the same ground.

**Reprojection and units** are the substance here: a DEM is in a geographic or
projected CRS with its own vertical units, and the world is metres about an
origin. The mapping (centre → local metric frame, elevation → metres, the
resample onto the world's extent) is the real work and belongs with the terrain
code, tested numerically.

**Tests.** Preset bases: assert each produces a height field in its intended
band (a canyon has a deep central trough; hills stay gentle). DEM sampling:
feed a small synthetic DEM and assert the sampled/reprojected field matches
expected metres at known points. Project round-trip for the `source` block.

**Docs.** `README.md` "What a project is" and "Limits" (which presets ship, what
DEM formats load, whether lat/long fetch is built); openglcontext-editor terrain
docs.

### What landed — **Done**, 2026-08-19

**The generator was parameterised first** (`OpenGLContext/loaders/tiles3d/procedural.py`).
The shipped field is four things added together, and `TerrainProfile` is how
much of each there is: hills, ridged mountains under a mask, a meandering
canyon, a dished basin — every amount in metres of relief and every scale in
metres on the ground. `terrain_height_for(profile)` builds a height function
from one; `SHIPPED_TERRAIN` is the profile `terrain_height` *is*, and a test
holds it against the numbers written out longhand, because worlds already baked
came from them. `fbm` and `ridged` are exposed so anything adding to the
landscape is made of the same grain.

**Presets** (`world/presets.py`) — `mountains`, `lakes`, `hills`, `canyon` and
the shipped landscape, each a tuned profile with a label and a sentence.
`PresetBase(name, relief, seed)`: `relief` makes a landscape too tall for a road
into one a road can be built through without changing what it looks like, and
`seed` gives another landscape of the same description.

**DEM import** (`world/dem.py`) — `read_hgt` reads an SRTM height file and
`DEMBase(path, centre, datum, relief)` puts it under a world at a point on the
Earth. The mapping from degrees to metres is a local tangent plane about the
centre, with the WGS 84 radii of curvature. Nothing is fetched: the file is one
the designer supplies, named in the project so a reopened track resolves to the
same ground.

**Provenance.** `openglcontext-editor/specs/ELEVATION-DATA.md` records the file
layout and naming (from the published mission documentation), WGS 84, and the
tangent-plane mathematics, with the code citing it by section. No GIS tool's
source was read; the specs README already ruled that channel out and the facts
were not in it.

**Editor.** A **Terrain** menu that cuts the track into a different landscape
and keeps the line, `--terrain` and `--dem`/`--centre`/`--datum` on the command
line, and a contour spacing that follows the landscape — a spacing that reads on
rolling hills draws a hatch over a mountain range.

**Guards.** `openglcontext/tests/unit/test_terrain_profile.py`,
`openglcontext-editor/tests/test_world_presets.py` (each preset asserted against
what it claims to be — a canyon has a trough, hills stay gentle, lake country
has ground under the waterline), `tests/test_world_dem.py` (against a height
file the test writes itself, and distances anyone can check with a calculator),
and the command-line cases in `glisteel-editor/tests/test_project.py`.

**Docs.** `openglcontext/docs/terrain.html`, both `README.md`s, and the spec.

---

## F. Land sculpting — raise and lower with fractal detail (item 5)

Builds on **C** (edit stack) and **B** (a `SculptTool` in the palette).

**Edit kind.** `SculptStroke` — a centre, a radius, a signed amount, a falloff,
and a **fractal-detail** term so a raised region gets natural small-scale
variation rather than a smooth dome. It evaluates vectorised over its bounded
rectangle (per **C**'s performance rule). Modulating the delta by the procedural
noise already in the terrain keeps a lifted hill in the same visual family as the
land around it.

**Tool.** A `SculptTool` (`ToolMode`) with raise/lower (button or modifier),
brush radius and strength (wheel or keys). Each stroke, or each drag, pushes one
`SculptStroke` onto the edit stack — one undo step per gesture, matching the
route editor's `begin_step`/`end_step` grouping in `editing.py`. Because the
plan view already draws "the ground as it will be baked", a raised hill appears
under the brush on settle, exactly as the road's earthworks do now.

**Interaction with the road.** The road settles onto the height *source*; a
sculpt under the alignment changes the road on the next settle. Order is defined
by the edit stack, and the road is derived after it — no new coupling.

**Tests.** Stroke math is pure: a raise lifts its centre by the amount, respects
the falloff to zero at the radius, adds bounded fractal detail, and leaves
samples outside the rectangle unchanged. Tool: a synthetic drag produces one
undoable stroke; undo removes it.

**Docs.** `README.md` "Tools"; the sculpt edit kind in openglcontext-editor.

### What landed — **Done**, 2026-08-19

`SculptStroke` (`world/sculpt.py`): a centre, a radius, a signed amount, a
falloff that reaches zero *at* the radius so a stroke never steps, and a
fractal-detail term. The detail **modulates the lift** rather than adding to
it, which is what keeps it inside the brush — at the rim there is no lift, so
there is nothing to vary — and makes it a share of the stroke, so a gentle
stroke gets gentle detail rather than turning to gravel.

`glisteel_editor/sculpting.py`: `LandEditor` (the brush, the strokes, the
history) and `SculptTool` (left raises, right lowers, wheel sizes the brush,
`[`/`]` change how hard it pushes, Escape abandons). One gesture is one stroke
and one undo however far the pointer travels.

**Two things the spine needed**, both in the engine: `ToolMode.on_wheel` /
`ToolManager.wheel`, so a brush can be sized without a key and the camera still
gets the notch no tool wanted; and `ToolMode.undo`/`redo` with
`ToolManager.undo`/`redo`, so **undo belongs to the tool in force**. The tools
edit different things — a route, a landscape, a set of springs — and one history
over all of them takes back whichever change came last regardless of what the
designer is working on.

**The brush is drawn.** A ring on the ground under the pointer, draped over the
land so on a hillside it says which ground it covers. It is what moves during a
gesture; the mesh, the contours, the road and its earthworks are rebuilt when
the pointer is let go, because doing that per mouse-move is ~300 ms a frame.

**Guards.** `openglcontext-editor/tests/test_world_sculpt.py`,
`glisteel-editor/tests/test_sculpting.py`, the palette-and-tools cases in
`tests/test_tools.py`, and the brush cases in `tests/test_scene.py`. Driven end
to end through the real window as well: click Sculpt in the palette, drag on the
map, and the ground under the stroke rises.

**Docs.** Both `README.md`s.

---

## G. Hydrology — water that wells up and flows downhill (item 4)

Builds on **C** and **B** (a `WaterTool`). The stronger of the designer's two
asks (a source that flows) subsumes the weaker (paint a river), so build the
source.

**Mechanism (openglcontext-editor `world/`).** From a **source point**, route
water downhill over the height field (steepest-descent / D8-style flow following
the gradient) until it reaches the water level or the map edge. The path becomes:

- a **`Channel` edit** on the height stack (carve a bed so the river reads in the
  terrain and the road crosses it as water, not a stripe), and
- a **water surface** along the path for the plan view and the bake.

Flow accumulation lets tributaries merge and the channel widen downstream, so a
"river" is the emergent thing rather than a painted stroke.

**Tool.** `WaterTool` places a source; the flow recomputes on settle (the same
"expensive work happens when the pointer is let go" rule the road already
follows, `controls.py` `on_settle`). The source point and its parameters are the
serialisable part; the channel is derived from source + height, so it recomputes
when the land is sculpted under it.

**Ordering vs sculpt.** Water is computed against the height *after* sculpt
edits, so raising land upstream reroutes the river — which is the natural
behaviour a designer expects.

**Tests.** On a known tilted/basin field, assert flow runs monotonically
downhill, terminates at the water level or an edge, and merges where paths meet.
Channel edit lowers the bed along the path and nowhere else. Pure, no GL.

**Docs.** `README.md` "Tools" and "Limits"; hydrology in openglcontext-editor.

### What landed — **Done**, 2026-08-19

`world/hydrology.py`: `Spring`, `flow_from`, `FlowPath`, `channels_for` and
`Channel`. From a spring the water is walked downhill until it reaches the
waterline, runs off the edge, or arrives somewhere it cannot leave — `water`,
`edge`, `basin`, `joined` or `lost`, said rather than guessed.

**Water fills a hollow and spills.** Every direction is tried at once and the
lowest taken; if nothing a step away is lower the same ring is tried further
out, up to eight steps. Without it a river stopped in the first dimple of a
noisy hillside: the shipped landscape gave nine-point rivers, and the same
springs now give forty-point ones. A hollow wider than the reach is a lake,
which is an answer.

**Rivers merge.** A path arriving within a step and a half of one already there
stops and adds its water to it, so the river below a junction cuts a wider,
deeper bed than either branch: `Channel` widens and deepens by a fixed amount
per doubling of what it carries.

**The bed is derived, not saved.** `Landscape.springs` is what the file holds;
`Landscape.channels()` works the beds out and keeps them against what they were
worked out *from*, so a sculpted hill or a moved spring reroutes the water and
nothing has to remember to say so. A bed in the file would be the river as the
land used to be.

**Editor.** `glisteel_editor/water.py` — `WaterEditor` and `WaterTool` (click to
place, drag to move, right-click to remove), the rivers and their springs drawn
on the plan view, and the ground rebuilt on settle.

**Guards.** `openglcontext-editor/tests/test_world_hydrology.py` (over a tilted
plane, a bowl, a V and a dimpled slope), `glisteel-editor/tests/test_water.py`,
and the water cases in `tests/test_scene.py`. Driven through the real window:
three springs on a mountain landscape, three rivers on the map.

**Docs.** Both `README.md`s, including the limit — a river is a carved bed with
water in it where it runs below the waterline, and flow is steepest-descent from
a point rather than a catchment model.

---

## H. Start and finish (item 6)

**Model.** A route today is points plus a `closed` flag (`project.py`). Add
endpoints: for a **closed circuit**, a start/finish line at a chosen point (which
also fixes the grid and lap timing); for an **open** route, an explicit start and
end. The world generator already reasons about the circuit for the grid and lap
timing (it reads the circuit from the tileset `extras`); the start position feeds
that, so it belongs in openglcontext-editor `world/route.py` (which already has a
note about "a junction, a start line") with the editor recording the choice.

**Tool / interaction.** With the palette in place, a "Set start/finish" tool
places the marker on the line; `scene.py` draws it (a distinct marker over the
guide, like the structure marks). It is one point index (plus a direction) on the
route, serialised with the route.

**Tests.** Placing start sets the index; bake carries it into the tileset
`extras` and the game's reader reads it back — `tests/test_baking.py` already
round-trips the circuit through the game's own reader and is the natural place to
assert the start comes with it.

**Docs.** `README.md` "Drawing"/"Baking".

### What landed — **Done**, 2026-08-19

`Route.start` (which point a lap begins at) and `Route.reversed` (which way
round it is driven), both in the file. `Route.plan()` turns the line round, so a
reversed circuit is reversed once rather than everywhere downstream, and
`Route.start_point()` answers where the line is — falling back to the first
point when the one under it has been taken out, because a lap still has to
begin.

`ProceduralWorld.start_at` takes that **world point** and
`start_station()` answers the station nearest it. Nearest rather than an index,
because the centreline a game gets is not the plan: it has been eased, draped
over the ground and re-sampled, and the point the designer put the line on is
what survives all of that. `RoadLayer.start` carries it into the tileset's
`extras` as `roads[0]['start']`.

**Editor.** `StartTool` (left click puts the line at the nearest point, right
click turns the circuit round) and a bar drawn **across** the line where the lap
begins — across rather than along, because a mark along the road is a road
marking.

**Guards.** `openglcontext-editor/tests/test_world_start.py`,
`glisteel-editor/tests/test_start.py`, the start cases in `tests/test_scene.py`,
and `tests/test_baking.py`, which bakes a world and reads the start back out of
the tileset the game opens.

---

## I. Snap the track to iso-height lines (item 7)

Builds on **D**'s contour extraction. When placing or dragging a route point with
snap on, pull it to the nearest point on the nearest contour (nearest iso-height),
so a designer can run a road *along* a hillside at near-constant grade.

**Where.** The snap is a small transform on the pointer's world position in the
editor's `editing.py` (`RouteEditor.append`/`insert`/`move`), using the engine's
height field and the shared contour/gradient machinery from **D**. A modifier key
or a palette toggle turns it on, so free placement stays the default. Snap-to
uses the height gradient: the nearest iso-height point is a short step along the
gradient from the pointer, which is cheaper and steadier than searching extracted
contour polylines.

**Tests.** On a known slope, a placed point lands on the target iso-height within
tolerance; with snap off the point is unchanged. Pure arithmetic.

**Docs.** `README.md` "Drawing".

### What landed — **Done**, 2026-08-19

`OpenGLContext/edit/surface.py` gains `height_gradient` and `snap_to_height`:
the nearest ground at a given height is a step along the gradient, exact in one
step for ground that rises evenly and a few more where it curves. `reach` caps
how far a point may be moved, because a contour half a kilometre away is not
what the pointer meant.

`RouteEditor` takes a height function and a snap, and `append`/`insert`/`move`
put the point on the iso-height **its neighbour is on** rather than the nearest
round one. That is the whole point: a road along a hillside runs at one
elevation, and each point taking its own nearest contour would step it up and
down the slope as the pointer wandered.

**Turning it on.** `h` toggles it; **shift does the other thing for one point**,
whichever way the mode is set, so one point on a contour costs no mode change
and neither does one off it. The height held follows the contour spacing on
screen, so a designer is aiming at a line that is actually on the map, and the
tool read-out says "Draw route -- holding 25 m".

**Guards.** `openglcontext/tests/unit/test_edit_isoheight.py`,
`glisteel-editor/tests/test_snap.py`.

**Docs.** `openglcontext/docs/editing.html`, `README.md` "Drawing".

---

## J. Switchbacks — a road that climbs (item 8)

**Today.** The route generator holds the alignment to a maximum grade by *moving
the line* (`world/route.py`: "The answer is not to give up on the grade. It is to
move the line"), and lifts onto a causeway below the waterline. A designer who
draws a hairpin up a slope currently has it smoothed toward the grade limit
rather than kept as a switchback.

**Fix (openglcontext-editor `world/route.py`).** Let the plan operation *keep*
tight, deliberate hairpins that exist to gain height, rather than easing them
away — recognise a designer-drawn switchback (a sharp reversal climbing a slope)
and hold its geometry while still applying the grade and cornering-radius limits
along each leg. This is an extension of the existing ease/hold-radius logic, not a
new subsystem.

**Interaction with sculpt and snap.** A switchback is exactly what the iso-height
snap (I) helps draw — legs along the contour, tight turns between them — so H/I/J
compose: snap lays the legs, the generator keeps the hairpins, start/finish sits
on the result.

**Tests.** A drawn hairpin on a slope survives generation as a switchback (the
reversal is preserved) while each leg still respects the grade and radius limits.
Extends the existing route-generation tests in openglcontext-editor.

**Docs.** openglcontext-editor road/route docs; `README.md` "Limits" updated
(what grades and switchbacks the generator now supports).

### What it turned out to be — **Done**, 2026-08-19

**Not what the plan expected.** A drawn plan's *plan* was never smoothed:
`follow_terrain` settles the **profile** and leaves the line alone, and
`ease_route` — which does move the line — is only used for the circuit the world
invents for itself. What a drawn route got instead was **no horizontal curve
treatment at all**: every vertex was a corner the road turned through at a
single point, which no car can take and which the alignment then had to be
settled around. A drawn hairpin was not eased away; it was undrivable.

**Fix (`world/route.py`).** `hold_corners` rounds each corner **in place** with
a circular fillet tangent to both legs, so the legs keep the direction and the
place they were drawn and only the corner changes. That is the opposite decision
from `hold_radius`, which relaxes the line towards its chords: right for a route
being *found*, wrong for one that was *drawn*. A fillet never takes more than
45% of either leg, so two corners on a short leg still fit and the radius comes
down instead; a vertex turning less than fifteen degrees is a sample of a curve
and is left alone; and the arc is drawn at the road's own spacing, because an
arc sampled more coarsely is re-sampled onto its own chords and the road turns
at the joins between them.

`ProceduralWorld.circuit()` applies it to any route it is given. A hairpin with
room gets the radius the design speed asks for; one with sixty metres between
its legs gets the tightest that fits, which is a corner rather than the vertex
it replaced — and either way the legs stay where the designer drew them.

**Guards.** `openglcontext-editor/tests/test_world_switchback.py`: the hairpin
still reverses, nothing ends up tighter than it was told, every leg is still on
the line, and the same plan relaxed instead moves off it.

**Docs.** openglcontext-editor `README.md` ("Corners a designer drew"),
glisteel-editor `README.md` ("Drawing").

## K. Seeing the land in three dimensions (item 0)

**Why.** The editor is a map, and a map is the right thing to *draw* on: a metre
is the same number of pixels everywhere and the line drawn is the line the world
gets. It is not the right thing to *judge* on. A designer who has just raised a
hill wants to look at it, and today the only way is to bake a world and drive
it — minutes of work to answer a question that takes a second to ask.

Shading and contours go a long way (D), and they are what make the map readable
at all. What they cannot do is answer "does that look right", which is the
question a landscape is finally judged by.

**Where.** The camera belongs in the engine, beside `MapView`: an orbiting view
over a point of interest is what every editor's preview is, and the second
editor built on this toolkit should not write it again.
`OpenGLContext/edit/mapview.py` gets a sibling.

**Shape of it.**

- **`OrbitView`** — a point on the ground it looks at, a heading, a pitch and a
  distance, and the two matrices a pass wants. The default pitch is the
  three-quarter view a designer means by "let me look at it": high enough to
  read the plan, low enough to read the relief.
- **`OrbitViewPlatform`** — reads the view rather than copying it, exactly as
  `MapViewPlatform` does, so orbiting is what moves the camera and there is no
  second copy of where the editor is looking.
- **The editor swaps between them.** One window, one scene, two cameras: a menu
  item and a key put the window into the three-quarter view and back, and the
  view looks at the middle of the map, so what was under the pointer is what is
  in front of the camera. The pointer orbits and dollies there; the tools stay
  on the map, where a click means a place rather than a ray.
- **The scene does not change.** The ground keeps its shaded relief and its
  contours: the shading is a reading of the shape, and it reads the same way
  from an angle. Nothing is rebuilt on the swap, so it is instant.

**What this deliberately is not.** A *split* view — map and perspective side by
side, both live — is the nicer product and is pass-level work: the render pass
takes the whole window, and drawing the scene twice per frame means a viewport
and scissor per pass, a second shadow-map and selection pass to pay for, and a
decision about which half the overlay belongs to. Worth doing; not this.

**Tests.** The camera is arithmetic — where it stands for a heading, a pitch and
a distance, that orbiting moves it round the point it is looking at rather than
moving the point, that it cannot be tipped past the poles, that framing a region
puts it in view. Headless. The editor's swap is a plain object holding two
platforms.

**Docs.** `openglcontext/docs/editing.html` beside the plan view; `README.md`
gains the key and says what the view is for and what it is not.

### What landed — **Done**, 2026-08-19

`OpenGLContext/edit/orbitview.py`: `OrbitView` (a point on the ground, a
heading, a pitch, a distance, and a perspective projection fitted to that
distance so the depth buffer's precision is where the ground is) and
`OrbitViewPlatform`. Orbiting leaves the subject where it is; the pitch stops
short of overhead and of the horizon, where a camera has no unique up-vector
and sees the ground edge-on. Setting a *position* on the platform works out the
heading, pitch and distance that put the camera there, so anything that moves a
camera by position moves this one.

**Editor.** `View → Look at it` and `p` swap the window's platform; `f` frames
the landscape in whichever view is in force. The three-quarter view starts where
the map was looking and takes in as much ground as the map was showing, and
going back puts the map where the camera was looking. `OrbitControls`
(`controls.py`) gives it the pointer: every button orbits and the wheel dollies,
because a click here is a ray rather than a place.

**Nothing is rebuilt on the swap**, so it is instant: the ground keeps its
shaded relief and its contours, which read the same way from an angle — the
shading *is* a reading of the shape.

**The scale read-out stopped lying.** A metre is the same number of pixels
everywhere on a map and nowhere in a perspective view, so `SCALE 2.56 m / pixel`
becomes `VIEW 2.81 km away, 47 deg up`. `Readout` also gained `maximumColumns`,
because a read-out whose value comes from the application — a message, a place
name — has no natural length, and one that runs across the screen crosses
whatever is anchored at the other end of it.

**Guards.** `openglcontext/tests/unit/test_edit_orbitview.py` (where the camera
stands, that orbiting turns it round the point rather than moving the point,
that it cannot be tipped past the poles or dollied into the ground, that the
point it looks at lands in the middle of the screen), the `OrbitControls` cases
in `glisteel-editor/tests/test_controls.py`, the read-out cases in
`tests/test_status.py` and `openglcontext/tests/unit/test_ui_hudwidgets.py`.

---

## Ordering and dependencies

```
A. Menu latency        ── independent, do first (usability)
B. Tool palette        ── spine for every new tool
C. Editable height     ── spine for terrain authoring
        │
        ├── D. Relief + contours ──┐
        │                          ├── I. Iso-height snap
        ├── E. DEM presets / latlong
        ├── F. Sculpt  (needs B, C)
        └── G. Hydrology (needs B, C; uses F ordering)

H. Start / finish  ── needs B; independent of terrain work
J. Switchbacks     ── needs route work; composes with I
```

Suggested sequence: **A → B → C → D → (E, F, G in any order) → H → I → J.**
A and B and C can proceed in parallel by different hands; D unlocks I; H is
independent and can land whenever the palette exists.

## Cross-cutting requirements (every phase)

- **Engine-first.** Reusable machinery lands in OpenGLContext or
  openglcontext-editor; the editor calls it. If a fix feels like it belongs in the
  editor, check whether a game editor would want it — if so, it is in the wrong
  place.
- **Red/Green TDD, headless.** The editor suite runs without a window; new logic
  goes in plain objects that take inputs and return data, per the "hoist the logic
  out of what a test cannot reach" rule. Write the failing test first.
- **Docs ship with the change.** `README.md` and the relevant engine/world docs
  are updated in the same piece of work; the phase report says which docs changed.
- **Provenance.** Any DEM format or elevation source gets a spec/citation; any
  copyleft reader triggers [../../CLEAN-ROOM.md](../../CLEAN-ROOM.md).
- **Performance headroom.** Height-field and hydrology work stays vectorised and
  spatially bounded; the bar is a heavier real game, not this editor.

---

## What is still open

- **The perspective view is a swap, not a split.** Map and three-quarter view
  side by side, both live, is pass-level work: the render pass takes the whole
  window. See **K**.
- **The tools are the map's.** In the three-quarter view the pointer orbits; a
  route drawn there would want a ray against the ground rather than a place on
  it.
- **The ground redraws when a gesture ends**, not while it is being dragged.
  Re-meshing the landscape and re-settling the road costs ~300 ms; the brush
  ring is what moves in the meantime. A lower-resolution preview mesh under the
  brush would close that.
- **Contours are not labelled** with their elevation on the map.
- **No file browser.** `Open` still reopens the file named on the command line,
  and an elevation file is named there too.
- **No lat/long fetch.** `DEMBase` reads a file the designer supplies; fetching
  a region from an open elevation service is not built, and the editor stays
  usable with no network because of it.

---
