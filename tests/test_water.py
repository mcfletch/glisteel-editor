"""Putting water on the map, and the river it makes.

Headless: a spring is a point, a river is what the ground does with it, and the
bed it cuts is arithmetic on the landscape's edit stack.
"""
import numpy as np
import pytest
from OpenGLContext.edit.tools import Pointer
from OpenGLContext_editor.world.hydrology import Spring

from glisteel_editor.project import Project, new_project
from glisteel_editor.water import WaterEditor, WaterTool


def _at(x, z, button=0):
    return Pointer(x=0.0, y=0.0, world=np.array([x, 0.0, z], dtype='d'),
                   button=button)


def _rig(**named):
    project = new_project(extent=2048.0)
    changed = []
    editor = WaterEditor(project.landscape,
                         on_change=lambda: changed.append(1), **named)
    return editor, project, changed


class TestPlacingASpring:
    def test_a_click_puts_water_down(self) -> None:
        editor, project, _changed = _rig()
        WaterTool(editor=editor).on_press(_at(100.0, -200.0))
        assert project.landscape.springs == [Spring(at=(100.0, -200.0))]

    def test_the_right_button_takes_one_away(self) -> None:
        editor, project, _changed = _rig()
        tool = WaterTool(editor=editor)
        tool.on_press(_at(100.0, -200.0))
        tool.on_press(_at(100.0, -200.0, button=2))
        assert project.landscape.springs == []

    def test_the_right_button_over_open_ground_is_left_alone(self) -> None:
        editor, _project, _changed = _rig()
        tool = WaterTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        assert not tool.on_press(_at(9000.0, 9000.0, button=2))

    def test_dragging_moves_the_spring_that_was_put_down(self) -> None:
        editor, project, _changed = _rig()
        tool = WaterTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(80.0, 40.0))
        assert project.landscape.springs == [Spring(at=(80.0, 40.0))]

    def test_several_springs_make_several_rivers(self) -> None:
        editor, project, _changed = _rig()
        tool = WaterTool(editor=editor)
        for where in ((-600.0, -600.0), (500.0, 300.0)):
            tool.on_press(_at(*where))
            tool.on_release(_at(*where))
        assert len(project.landscape.springs) == 2

    def test_it_says_the_land_changed(self) -> None:
        editor, _project, changed = _rig()
        WaterTool(editor=editor).on_press(_at(0.0, 0.0))
        assert changed

    def test_it_leaves_a_click_on_nothing_alone(self) -> None:
        editor, project, _changed = _rig()
        assert not WaterTool(editor=editor).on_press(Pointer(world=None))
        assert project.landscape.springs == []


class TestTakingItBack:
    def test_undo_removes_the_spring(self) -> None:
        editor, project, _changed = _rig()
        WaterTool(editor=editor).on_press(_at(0.0, 0.0))
        assert editor.undo()
        assert project.landscape.springs == []

    def test_redo_puts_it_back(self) -> None:
        editor, project, _changed = _rig()
        WaterTool(editor=editor).on_press(_at(0.0, 0.0))
        editor.undo()
        assert editor.redo()
        assert len(project.landscape.springs) == 1

    def test_nothing_to_undo_says_so(self) -> None:
        editor, _project, _changed = _rig()
        assert not editor.undo()


class TestTheRiverItMakes:
    def _project_with_water(self, at=(-800.0, 700.0)):
        project = new_project(extent=2048.0)
        project.landscape.springs.append(Spring(at=at))
        return project

    def test_the_landscape_grows_a_channel(self) -> None:
        project = self._project_with_water()
        assert project.landscape.channels()

    def test_the_ground_along_it_is_lower_than_it_was(self) -> None:
        project = self._project_with_water()
        channel = project.landscape.channels()[0]
        middle = channel.points[len(channel.points) // 2]
        x = np.asarray([middle[0]])
        z = np.asarray([middle[1]])
        before = float(project.landscape.source.height_fn()(x, z)[0])
        after = float(project.landscape.ground().height_fn()(x, z)[0])
        assert after < before

    def test_the_world_is_built_on_the_ground_with_its_rivers(self) -> None:
        project = self._project_with_water()
        channel = project.landscape.channels()[0]
        middle = channel.points[len(channel.points) // 2]
        x = np.asarray([middle[0]])
        z = np.asarray([middle[1]])
        assert float(project.world().natural()(x, z)[0]) \
            == pytest.approx(float(project.landscape.ground().height_fn()(x, z)[0]))

    def test_a_landscape_with_no_springs_is_the_land_as_it_was(self) -> None:
        project = new_project(extent=2048.0)
        assert project.landscape.channels() == []
        assert project.landscape.ground() is project.landscape.source

    def test_the_river_is_worked_out_once_and_kept(self) -> None:
        project = self._project_with_water()
        assert project.landscape.channels() is project.landscape.channels()

    def test_moving_the_spring_moves_the_river(self) -> None:
        project = self._project_with_water()
        before = project.landscape.channels()[0].points.copy()
        project.landscape.springs[0] = Spring(at=(-700.0, 640.0))
        after = project.landscape.channels()[0].points
        assert not np.array_equal(before[:1], after[:1])

    def test_sculpting_the_land_reroutes_it(self) -> None:
        from OpenGLContext_editor.world.sculpt import SculptStroke
        project = self._project_with_water()
        before = project.landscape.channels()[0].points.copy()
        project.landscape.source.edits.append(
            SculptStroke(centre=tuple(before[3]), radius=400.0, amount=120.0))
        after = project.landscape.channels()[0].points
        assert not np.array_equal(before, after)


class TestTheFile:
    def test_a_spring_is_saved_with_the_project(self, tmp_path) -> None:
        project = new_project(extent=2048.0)
        project.landscape.springs.append(Spring(at=(12.0, -34.0)))
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        assert Project.open(path).landscape.springs == [Spring(at=(12.0, -34.0))]

    def test_the_bed_is_not_saved_because_it_is_worked_out(self, tmp_path) -> None:
        """A carved bed in the file would be the river as the land used to be."""
        import json
        project = new_project(extent=2048.0)
        project.landscape.springs.append(Spring(at=(-800.0, 700.0)))
        project.landscape.channels()
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        with open(path) as handle:
            document = json.load(handle)
        assert document['landscape']['source']['edits'] == []
        assert document['landscape']['springs'] == [{'at': [-800.0, 700.0]}]


class TestTakingBackASpringThatWasMoved:
    """A spring reroutes a river and everything downstream of the ground.

    The route editor already says why a drag has to be one step rather than one
    per pointer movement, and why Escape has to put a dragged thing back. The
    same is true here, and for the same reason: a gesture that cannot be taken
    back is a landscape nobody will experiment with.
    """

    def test_moving_a_spring_can_be_taken_back(self) -> None:
        editor, project, _changed = _rig()
        editor.add((100.0, -200.0))
        editor.begin_step()
        editor.move(0, (300.0, -50.0))
        editor.end_step()
        assert editor.undo()
        assert project.landscape.springs[0].at == (100.0, -200.0)

    def test_taking_it_back_does_not_take_the_spring_away(self) -> None:
        editor, project, _changed = _rig()
        editor.add((100.0, -200.0))
        editor.begin_step()
        editor.move(0, (300.0, -50.0))
        editor.end_step()
        editor.undo()
        assert len(project.landscape.springs) == 1

    def test_a_drag_is_one_step_however_many_movements_it_is(self) -> None:
        editor, project, _changed = _rig()
        editor.add((0.0, 0.0))
        editor.begin_step()
        for step in range(20):
            editor.move(0, (float(step) * 10.0, 0.0))
        editor.end_step()
        editor.undo()
        assert project.landscape.springs[0].at == (0.0, 0.0)

    def test_the_tool_groups_a_drag_of_an_existing_spring(self) -> None:
        editor, project, _changed = _rig()
        editor.add((0.0, 0.0))
        tool = WaterTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(400.0, 400.0))
        tool.on_release(_at(400.0, 400.0))
        assert editor.undo()
        assert project.landscape.springs[0].at == (0.0, 0.0)

    def test_escape_puts_a_dragged_spring_back(self) -> None:
        editor, project, _changed = _rig()
        editor.add((0.0, 0.0))
        tool = WaterTool(editor=editor)
        tool.on_press(_at(0.0, 0.0))
        tool.on_drag(_at(400.0, 400.0))
        tool.cancel()
        assert project.landscape.springs[0].at == (0.0, 0.0)

    def test_escape_while_placing_a_new_one_takes_it_away_again(self) -> None:
        editor, project, _changed = _rig()
        tool = WaterTool(editor=editor)
        tool.on_press(_at(50.0, 50.0))
        tool.on_drag(_at(400.0, 400.0))
        tool.cancel()
        assert project.landscape.springs == []
