"""``python -m glisteel_editor`` -- the same as the ``glisteel-editor`` command."""
import sys

from glisteel_editor.app import main

if __name__ == '__main__':
    sys.exit(main())
