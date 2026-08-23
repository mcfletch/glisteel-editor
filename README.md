# GLinting Steel — the track editor

Draw a circuit on a landscape, watch the road settle onto the ground under it,
and bake a world the game streams and drives.

```bash
pip install glisteel-editor
glisteel-editor              # a fresh landscape to draw on
```

The window is a **map**: the landscape from straight above, orthographic, so a
metre is the same number of pixels wherever it is and the line drawn on it is
the line the world gets. Click the ground to put a point down, and again, until
the circuit closes. Press `p` to look at what you have from an angle, and again
to go back. `File → Bake a world` writes it out; `File → Drive it` puts you in
the car.

## Tools

A strip down the left of the window says what the pointer is for; click a
button to change it. The menus keep the operations that apply to the whole
track — new, open, save, bake, drive, and what the view shows.

| Tool | The pointer |
|---|---|
| **Draw route** | draws and adjusts the line (below) |
| **Start / finish** | says where a lap begins, and which way round it goes |
| **Sculpt land** | raises and lowers the ground (below) |
| **Place water** | puts a spring down and lets it run downhill (below) |
| **Pan/zoom** | moves the map, so a left drag close in does not gain points |

Whatever the tool in force does not want still moves the map: a right drag pans,
and the wheel zooms in every tool but Sculpt, where it sizes the brush.

`ctrl-z` takes back what the **tool in force** last did, so undo while sculpting
takes back a stroke and undo while drawing takes back a point. The tools edit
different things, and one history over all of them would take back whichever
change happened to come last.

## Drawing

With **Draw route** in force:

| | |
|---|---|
| left click on the ground | put a point at the end of the line |
| left click *on* the line | put one in there, between the two it fell between |
| left drag a point | move it — Escape puts it back |
| right click a point | take it out |
| right drag | move the map |
| wheel | zoom about the pointer |
| `delete` | take out the point under the pointer |
| `h` | hold the line to a height (below) |
| `shift` while placing | do the other thing about the height, for one point |
| `ctrl-z` / `ctrl-y` | undo, redo |
| `f` | frame the whole landscape |

The road is regenerated when you let go, not while you are dragging: settling an
alignment and cutting its earthworks is a fifth of a second of work, and doing
it per mouse-move would make the drag a slideshow. What is drawn is the ground
**with its earthworks** — a designer who cannot see the cutting cannot see what
the line is doing to the landscape.

**Corners are rounded, not opened out.** A point you put down is a corner, and
the road turns through the whole of one at a single vertex, which no car can
take. Each is replaced by the tightest arc the speed allows — or the tightest
the legs have room for — with the legs left where you drew them. That is what
makes a **switchback** work: draw a hairpin to climb a slope and you get a
hairpin, not a sweep across the hillside.

**The corners you draw are the corners you get.** The generator invents varied
corners for a circuit it draws itself; a line *you* drew is held to the one
design radius, because your corners are already your decision. What your line
does get is everything the road works out from it and from the land: how fast
each stretch is laid out for, where it may climb harder than the rest, which
stretches keep the ground's own bumps and which are ironed flat, where the trees
are cut back so you can see round a bend, and where it is built wide enough to
get past somebody. Draw a tight corner and it stays tight — and the road slows,
roughens and opens out around it on its own.

**Corners are banked.** The road leans into each of them, by as much as that
corner needs to hold the speed the track is laid out for and no more, so a
gentle sweeper leans hardly at all and a tight one leans to the limit. It leans
up to one in ten — the steepest an ordinary road is built to, not an oval's
banking — and the change is spread over some seventy metres of the approach, so
you arrive at a corner already leaning rather than rolling once you are in it.

What banking buys you is **tighter corners at the same speed**: 270 m of radius
instead of 315 m, which is a quarter less hillside per corner and a line you can
draw through country a flat road has to sweep across. The plan view draws the
lean, so what you see on the corner you drew is what you will drive.

### Holding a height

Press `h` and a point you place or drag is pulled onto the iso-height its
neighbour is on, so the road runs *along* a hillside at one elevation rather
than up and down it — which is how a road holds a grade round a mountain. The
height it holds is the contour spacing the View menu is set to, so you are
aiming at a line that is actually on the map, and the read-out says so.

`shift` does the other thing for one point, whichever way the mode is set: one
point on a contour without turning the mode on, or one off it without turning
it off.

### Where a lap begins

With **Start / finish** in force, click the line to put the start where you
clicked; right-click to drive the circuit the other way round. The bar across
the line is where the grid stands and where the timing counts from, and it goes
into the baked world so the game starts you there.

### Water

With **Place water** in force, click to put a spring down; the river runs from
it downhill when you let go, and stops where it reaches the waterline, the edge
of the map, or a hollow it cannot fill its way out of. Drag a spring to move it,
right-click to take it away.

Rivers that meet merge, and the one below a junction cuts a wider, deeper bed.
The bed is part of the landscape — the road crosses a river as water rather than
as a stripe — and it is *worked out* rather than saved: raise ground upstream
with the brush and the river finds another way down.

## Shaping the land

With **Sculpt land** in force, a ring on the map shows what the brush covers.

| | |
|---|---|
| left drag | raise the ground under the brush |
| right drag | lower it |
| wheel | make the brush wider or narrower |
| `[` / `]` | change how hard it pushes |
| escape | abandon the stroke being made |

One gesture is one stroke and one undo, however far the pointer travels. The
stroke carries fractal detail as a share of its lift, so a raised hill reads as
land rather than as a bubble; the ring is what moves while you drag, and the
ground, the road and its earthworks are rebuilt when you let go.

The strokes are part of the landscape, so they are saved with the project and
they are what the road settles onto: raise ground under the line and the road
climbs it on the next settle.

## Choosing the landscape

The **Terrain** menu cuts the track into a different landscape, keeping the line
you drew:

| Landscape | What you get |
|---|---|
| The shipped landscape | hill country with a range, a river canyon and a lake basin |
| Dramatic mountains | ranges over most of the map, rising most of a kilometre |
| Lakes | low country dished into broad basins that flood |
| Rolling hills | nothing steeper than a road can climb, anywhere |
| Canyon | a gorge three hundred metres deep across a high plain |

The contour spacing follows the choice: a spacing that reads on rolling hills
draws a hatch over a mountain range, so the landscape picks one and the View
menu overrides it.

A new track can also be started on real ground:

```bash
glisteel-editor --terrain canyon
glisteel-editor --dem N47E008.hgt --centre 47.5,8.5 --datum 0
```

`--dem` takes an SRTM `.hgt` file you supply — nothing is fetched — and
`--centre` says where on the Earth the middle of the map is. `--datum` is how
many metres above the waterline that point sits, since real ground is hundreds
of metres above the sea and a world whose waterline is at zero would be
underwater.

## Looking at it

Press `p`, or **View → Look at it**, and the window shows the same scene from a
three-quarter angle: the land with its shape in it, the road with its bridges
and bores, the contours draped over the ground. Drag to swing the camera round
what it is looking at, wheel to move in and out, `f` to take in the whole
landscape, `p` again to go back to the map.

The map is what a line is drawn on — a metre is the same number of pixels
wherever it is, so the line drawn is the line the world gets. This is what the
land is *judged* on: shading and contours say how high the ground is, and only
looking at it says whether it looks right.

The swap is instant and nothing is rebuilt, and it starts where the map was
looking, so what was under the pointer is what is in front of the camera. The
tools stay on the map: here the pointer is the camera's.

## Reading the land

The plan view draws the land two ways at once, because either alone leaves you
guessing:

- **Shaded relief** puts a fixed low sun on the ground's own slope, so a ridge
  and a valley are different colours rather than the same green. The land is
  steepened before it is lit, because country a road can be built through is
  gentle and shading it honestly gives a flat sheet; the ground is still drawn
  at the height it really is.
- **Contours** say by how much. They are the lines a road held to a grade is
  drawn against, at 10, 25, 50 or 100 metres, of the *landscape* rather than of
  the baked ground — so a road's earthworks do not redraw the map you are
  measuring against.

Both are on the **View** menu, and both turn off when the line alone is what you
are reading.

## What a project is

Not the world. The world is baked, is large, and is thrown away and made again
whenever a decision changes. A project is the handful of decisions that produced
it — which landscape, and what line was drawn across it. It is JSON, and a
designer can read it:

```json
{
  "generator": "glisteel-editor",
  "version": 2,
  "name": "Untitled",
  "landscape": { "extent": 2048.0, "seed": 11, "resolution": 33,
                 "treeDensity": 0.004,
                 "source": { "base": { "kind": "procedural", "relief": 0.5 },
                             "edits": [] },
                 "springs": [ { "at": [-800.0, 700.0] } ] },
  "routes": [ { "name": "circuit", "closed": true,
                "points": [[-700.0, 0.0], [-560.0, 400.0]] } ]
}
```

`landscape.source` is where the ground comes from: a **base** — the shipped
procedural terrain, at a `relief` that multiplies its height — and an ordered
stack of **edits** on top of it, each a bounded change to a region. Applying
them in order is what makes one edit build on the last. A file written before
there was a source block has none, and opens as the landscape it always was.

`landscape.springs` is where water wells up. The rivers are **worked out** from
those and the land rather than saved: a bed written down would be the river as
the land used to be, and would stay there when the land moved.

Points are `(x, z)` in world metres, in the order they were drawn, with no
heights: a route is a *plan*, and where the road actually runs is what the
generator works out from the ground under it — smoothed, held to a maximum
grade, rounded off for the speed it is meant to be driven at, and lifted onto a
causeway where it would otherwise run below the waterline.

## Baking

`File → Bake a world` writes a 3D Tiles world beside the project file, in
`<project>-world/`. The circuit goes into the tileset's `extras` along with it,
which is how the game finds the track in what it streams: the starting grid, the
lap timing and the autopilot all read it from there.

```bash
glisteel mytrack-world/tileset.json
```

## What is where

The editor is deliberately thin. The landscape, the road generation and the
baker belong to
[OpenGLContext-editor](https://github.com/mcfletch/openglcontext-editor); the
plan view, the tool modes and the menus belong to the engine's
[editor toolkit](https://github.com/mcfletch/openglcontext/blob/main/docs/editing.html).

| Module | Holds |
|---|---|
| `project.py` | a designer's decisions, and the file they live in |
| `editing.py` | the line being drawn, what the pointer does to it, and what it was |
| `sculpting.py` | the brush, the strokes made with it, and taking them back |
| `water.py` | where water wells up, and taking it back |
| `controls.py` | what the pointer did, and what the map and the tools do about it |
| `scene.py` | what the plan view draws: the land, the line, the road |
| `status.py` | the five things the editor tells you |
| `app.py` | the window, the menus, the tool palette, and baking |

## Limits

- **Five landscapes, or a file.** The shipped procedural terrain and four
  presets, at a size and a relief, or an SRTM `.hgt` elevation file you supply.
  Nothing is fetched over the network, and there is no file browser: an
  elevation file is named on the command line.
- **Contours are drawn, not laid out.** They are extracted from the height field
  at the interval you choose and drawn over the ground; nothing labels them with
  their elevation on the map yet.
- **One route per project.** The model holds a list; the interface draws the
  first.
- **The perspective view is a swap, not a split.** One window shows the map or
  the three-quarter view, not both at once, and you cannot draw in the
  three-quarter view.
- **Undo belongs to the tool in force.** Changing the landscape from the Terrain
  menu, or its size, is not on any history. Within a tool, one gesture is one
  step: a point or a spring dragged across the map is taken back in one, and
  Escape mid-drag puts it back where it started.
- **A river is a carved bed**, with water in it where it runs below the
  waterline. A stream down a mountainside is a valley rather than a ribbon of
  water.
- **The ground is redrawn when a stroke ends**, not while it is being dragged:
  re-meshing the landscape and re-settling the road per pointer movement would
  make the gesture a slideshow. The brush ring is what moves in the meantime.
- **`Open` reopens the file named on the command line** rather than putting up a
  file browser. `New` and `Open` both ask before replacing a track that has
  changes not in a file, as `Quit` does.
- **A project file is written whole or not at all.** It goes to a temporary file
  beside the target and is moved onto it, so a save interrupted by a full disk
  or a lost machine leaves the previous version rather than nothing. It is UTF-8,
  so a track named in any language reads the same on another machine.

## Developing

```bash
pip install -e ".[dev]"
pytest
```

The suite runs headless and without a window: a project is data, an edit is
arithmetic on a list of points, and a click is a position and a button.
`tests/test_baking.py` draws a circuit, bakes it, and reads the track back out
of the tileset through the game's own reader.

Baking is seconds of work rather than milliseconds, and those tests are most of
what the suite costs, so they carry a `slow` marker. A working loop skips them;
a full run does not:

```bash
pytest -m "not slow"        # while editing
pytest                      # before committing
```

What the tests hand the editor -- a pointer over a point of ground, a route, a
project on the standard landscape -- comes from `tests/support.py`, so the way
those are made up is written down once. A test says what it is about at the call
site (`support.project(support.ring_points(radius=420.0, count=16))`) and
nothing else.

## Licence

BSD-3-Clause; see [license.txt](license.txt).
