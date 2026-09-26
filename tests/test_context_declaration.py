"""What the editor's window is: GLFW, and no navigation beside its views."""
from OpenGLContext.context import Context
from OpenGLContext.ui.overlay import OverlayStackMixin

from glisteel_editor.app import EditorContext


def test_it_is_a_context_with_the_overlay():
    assert issubclass(EditorContext, Context)
    assert issubclass(EditorContext, OverlayStackMixin)


def test_it_opens_a_glfw_window():
    assert EditorContext.windowSystemName == 'glfw'


def test_its_views_are_all_that_move_the_cameras():
    """No movement mode, and no free-fly camera bound to the arrow keys the
    tools move control points with."""
    assert not EditorContext.resolveDefinition().navigation
