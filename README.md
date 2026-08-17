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
the circuit closes. `File → Bake a world` writes it out; `File → Drive it` puts
you in the car.

## Drawing

| | |
|---|---|
| left click on the ground | put a point at the end of the line |
| left click *on* the line | put one in there, between the two it fell between |
| left drag a point | move it — Escape puts it back |
| right click a point | take it out |
| right drag | move the map |
| wheel | zoom about the pointer |
| `delete` | take out the point under the pointer |
| `f` | frame the whole landscape |

The road is regenerated when you let go, not while you are dragging: settling an
alignment and cutting its earthworks is a fifth of a second of work, and doing
it per mouse-move would make the drag a slideshow. What is drawn is the ground
**with its earthworks** — a designer who cannot see the cutting cannot see what
the line is doing to the landscape.

## What a project is

Not the world. The world is baked, is large, and is thrown away and made again
whenever a decision changes. A project is the handful of decisions that produced
it — which landscape, and what line was drawn across it. It is JSON, and a
designer can read it:

```json
{
  "generator": "glisteel-editor",
  "version": 1,
  "name": "Untitled",
  "landscape": { "extent": 2048.0, "seed": 11, "resolution": 33,
                 "treeDensity": 0.004 },
  "routes": [ { "name": "circuit", "closed": true,
                "points": [[-700.0, 0.0], [-560.0, 400.0]] } ]
}
```

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
| `editing.py` | the line being drawn, and what the pointer does to it |
| `controls.py` | what the pointer did, and what the map and the tools do about it |
| `scene.py` | what the plan view draws: the land, the line, the road |
| `status.py` | the five things the editor tells you |
| `app.py` | the window, the menus, and baking |

## Limits

- **One landscape.** The shipped procedural terrain, at a size and a seed. Real
  elevation is the terrain pipeline's next piece of work.
- **One route per project.** The model holds a list; the interface draws the
  first.
- **No undo.** Escape abandons a drag; nothing brings back a point that has been
  taken out.
- **`Open` reopens the file named on the command line** rather than putting up a
  file browser.

## Developing

```bash
pip install -e ".[dev]"
pytest
```

The suite runs headless and without a window: a project is data, an edit is
arithmetic on a list of points, and a click is a position and a button.
`tests/test_baking.py` draws a circuit, bakes it, and reads the track back out
of the tileset through the game's own reader.

## Licence

BSD-3-Clause; see [license.txt](license.txt).
