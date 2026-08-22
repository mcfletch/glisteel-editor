"""Saying where a lap begins, and which way round it goes.

Headless: the start is a point on the line and a direction, and both are one
number in the project file.
"""
import numpy as np
import pytest
from support import pointer_at as _at, pointer_over_nothing

from glisteel_editor.editing import RouteEditor, StartTool
from glisteel_editor.project import Project, Route, new_project

SQUARE = [(-300.0, -300.0), (300.0, -300.0), (300.0, 300.0), (-300.0, 300.0)]


def _rig(points=SQUARE):
    project = new_project(extent=2048.0, points=points)
    editor = RouteEditor(project.route())
    return editor, project


class TestWhereALapBegins:
    def test_a_fresh_route_begins_at_its_first_point(self) -> None:
        _editor, project = _rig()
        assert project.route().start == 0

    def test_clicking_the_line_moves_the_start_to_the_nearest_point(self) -> None:
        editor, project = _rig()
        StartTool(editor=editor).on_press(_at(290.0, 280.0))
        assert project.route().start == 2

    def test_it_takes_the_point_it_is_nearest(self) -> None:
        editor, project = _rig()
        StartTool(editor=editor).on_press(_at(-310.0, 290.0))
        assert project.route().start == 3

    def test_a_click_miles_from_the_line_is_left_alone(self) -> None:
        editor, project = _rig()
        assert not StartTool(editor=editor).on_press(_at(9000.0, 9000.0))
        assert project.route().start == 0

    def test_a_click_over_nothing_is_left_alone(self) -> None:
        editor, _project = _rig()
        assert not StartTool(editor=editor).on_press(pointer_over_nothing())

    def test_a_route_with_no_points_takes_nothing(self) -> None:
        editor, _project = _rig(points=[])
        assert not StartTool(editor=editor).on_press(_at(0.0, 0.0))


class TestWhichWayRound:
    def test_a_fresh_route_runs_the_way_it_was_drawn(self) -> None:
        _editor, project = _rig()
        assert not project.route().reversed

    def test_the_right_button_turns_it_round(self) -> None:
        editor, project = _rig()
        StartTool(editor=editor).on_press(_at(290.0, -290.0, button=2))
        assert project.route().reversed

    def test_and_back_again(self) -> None:
        editor, project = _rig()
        tool = StartTool(editor=editor)
        tool.on_press(_at(290.0, -290.0, button=2))
        tool.on_press(_at(290.0, -290.0, button=2))
        assert not project.route().reversed

    def test_the_plan_the_generator_gets_runs_that_way(self) -> None:
        _editor, project = _rig()
        forward = project.route().plan()
        project.route().reversed = True
        backward = project.route().plan()
        assert np.allclose(backward[0], forward[0])
        assert np.allclose(backward[1], forward[-1])


class TestTakingItBack:
    def test_undo_puts_the_start_back(self) -> None:
        editor, project = _rig()
        StartTool(editor=editor).on_press(_at(290.0, 280.0))
        assert editor.undo()
        assert project.route().start == 0

    def test_undo_puts_the_direction_back(self) -> None:
        editor, project = _rig()
        StartTool(editor=editor).on_press(_at(290.0, -290.0, button=2))
        assert editor.undo()
        assert not project.route().reversed


class TestWhatTheProjectRemembers:
    def test_the_start_survives_being_saved(self, tmp_path) -> None:
        _editor, project = _rig()
        project.route().start = 2
        project.route().reversed = True
        path = str(tmp_path / 'track.glisteel')
        project.save(path)
        route = Project.open(path).route()
        assert route.start == 2 and route.reversed

    def test_a_track_written_before_there_was_one_begins_at_its_first_point(self) -> None:
        route = Route.from_json({'name': 'circuit', 'closed': True,
                                 'points': [[0.0, 0.0], [10.0, 0.0]]})
        assert route.start == 0 and not route.reversed

    def test_a_start_beyond_the_line_reads_as_its_first_point(self) -> None:
        """A point was taken out from under it; a lap still has to begin."""
        route = Route(name='circuit', points=[(0.0, 0.0), (10.0, 0.0)], start=9)
        assert route.start_point() == (0.0, 0.0)

    def test_the_world_is_told_where_it_is(self) -> None:
        _editor, project = _rig()
        project.route().start = 2
        world = project.world()
        assert world.start_at == pytest.approx(SQUARE[2])
