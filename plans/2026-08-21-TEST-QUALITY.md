# Test quality: one bake, and one way of making up a project

**Landed 2026-08-21.** A review of `tests/` for runtime, organisation and shared
code, and the changes that came of it. 375 tests before, 380 after (the five new
ones are the doctests in `tests/support.py`); green before and after.

## The measurement

| | before | after |
|---|---|---|
| whole suite | 79 s | 69 s |
| `tests/test_baking.py` | 42 s of bakes | 27 s |
| whole suite, `-m "not slow"` | — | 42 s |

## Where the time was going

Four tests baked a world, at about 10.5 s each, and two of those four baked the
*same* world: a track with a river across it, asked once whether the bake
produced tiles and once whether a tile carries the river. One bake answers both,
and it is now a module-scoped fixture, as the main bake already was.

What is left is three bakes, and they are three different worlds. That is the
cost of the thing the editor is for, so it is **marked rather than removed**:
`slow` is registered in `pyproject.toml`, `test_baking.py` carries it at module
level, and a working loop is `pytest -m "not slow"` at 42 s while a full run is
still the default.

## What was written more than once

Every test here is a designer doing something with the pointer to a route drawn
on a landscape, so nearly every test made up the same three things. Five files
defined the same `_at(x, z)` pointer factory, four built the same
`Project(name=..., landscape=Landscape(extent=2048.0, seed=11), routes=[...])`,
and three wrote out the same ring of plan points.

`tests/support.py` now holds `pointer_at`, `pointer_over_nothing`,
`ring_points`, `route` and `project`, with doctests. The landscape they build on
is one landscape (`EXTENT`, `SEED`), so a height read off it in one test is the
same height in another, and a test that wants a different one says so as an
argument.

`pointer_over_nothing()` earns its name: five tests ask a tool what it does
about a click over the sky, which is a thing worth having a name for rather than
a `Pointer(world=None)` written out again.

## Organisation

`tests/test_baking.py` had its `if __name__ == '__main__'` block in the *middle*
of the file, with two test classes after it, and two tests re-imported numpy
inside themselves. Both tidied.

## Still open

`test_a_chosen_start_travels_into_the_world` bakes a third world to read one
number back out of the tileset. It is a different project from the shared one --
the start is moved before baking -- so it cannot share; a cheaper way to assert
the same thing would have to come from the baker rather than from the test.
