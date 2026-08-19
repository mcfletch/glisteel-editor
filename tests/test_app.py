"""The decisions the editor's window makes, without the window.

A menu item that replaces the project a designer is working on has to ask first,
and one that does not is how an afternoon's work disappears. Whether to ask is a
question about a project, so it is answered here and the window's job is to put
the question.
"""
from glisteel_editor.app import bake_directory, would_lose_work
from glisteel_editor.project import new_project


class TestWhetherReplacingTheProjectLosesWork:
    def test_work_nobody_has_saved_would_be_lost(self) -> None:
        project = new_project(points=[(0.0, 0.0), (100.0, 0.0)])
        project.touch()
        assert would_lose_work(project)

    def test_a_project_that_is_saved_would_not(self, tmp_path) -> None:
        project = new_project(points=[(0.0, 0.0), (100.0, 0.0)])
        project.save(str(tmp_path / 'circuit.glisteel'))
        assert not would_lose_work(project)

    def test_an_untouched_project_would_not(self) -> None:
        assert not would_lose_work(new_project())

    def test_there_is_nothing_to_lose_before_there_is_a_project(self) -> None:
        assert not would_lose_work(None)

    def test_saving_makes_it_safe_to_replace(self, tmp_path) -> None:
        project = new_project(points=[(0.0, 0.0), (100.0, 0.0)])
        project.touch()
        assert would_lose_work(project)
        project.save(str(tmp_path / 'circuit.glisteel'))
        assert not would_lose_work(project)


class TestWhereABakeGoes:
    def test_beside_the_project_file(self, tmp_path) -> None:
        project = new_project()
        project.path = str(tmp_path / 'monaco.glisteel')
        assert bake_directory(project) == str(tmp_path / 'monaco-world')

    def test_a_project_with_no_file_is_named_after_itself(self) -> None:
        found = bake_directory(new_project(name='Ashdown'))
        assert found.endswith('Ashdown-world')
