# glisteel-editor remediation plan

Status: **Planned** — 2026-08-19

A designer sat down with the track editor and wrote up what stops them getting a
track built. This plan takes that list, decides where each fix belongs, and puts
the items in an order where the foundations land before the tools that stand on
them.

## The list, verbatim

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
