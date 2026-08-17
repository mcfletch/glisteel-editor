"""The GLinting Steel track editor.

Draw a circuit on a landscape, watch the road settle onto the ground under it,
and bake a world the game streams and drives.

The editor owns almost none of that. The landscape, the road generation and the
baker are :mod:`OpenGLContext_editor`; the map view, the tool modes and the
menus are :mod:`OpenGLContext.edit` and :mod:`OpenGLContext.ui`. What is here
is the *project* -- a designer's decisions and the file they live in -- and the
application that puts the rest on screen.
"""

__version__ = '0.1.0'
