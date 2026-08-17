"""What the editor tells the designer.

Headless: a read-out is a string with a label on it.
"""
import pytest

from glisteel_editor.status import EditorStatus


def _shown(**named):
    status = EditorStatus()
    status.show(**named)
    return status


class TestWhatItSays:
    def test_the_track_is_named(self) -> None:
        assert _shown(title='monaco*').title.value == 'monaco*'

    def test_the_route_is_counted_and_measured(self) -> None:
        value = _shown(points=7, length=4636.0).route.value
        assert '7 points' in value and '4.64 km' in value

    def test_a_short_route_is_in_metres(self) -> None:
        assert '850 m' in _shown(points=2, length=850.0).route.value

    def test_the_scale_is_metres_per_pixel(self) -> None:
        assert '/ pixel' in _shown(scale=2.5).scale.value

    def test_a_close_scale_is_given_to_the_centimetre(self) -> None:
        assert '0.25 m' in _shown(scale=0.25).scale.value

    def test_the_tool_in_force_is_named(self) -> None:
        assert _shown(tool='Draw route').tool.value == 'Draw route'


class TestTheLastThingThatHappened:
    def test_it_shows_a_message(self) -> None:
        status = EditorStatus()
        status.message = 'Saved monaco.glisteel'
        assert status.note.value == 'Saved monaco.glisteel'

    def test_it_reads_back(self) -> None:
        status = EditorStatus()
        status.message = 'Baked 341 tiles'
        assert status.message == 'Baked 341 tiles'

    def test_showing_the_state_does_not_wipe_it(self) -> None:
        """The message is what just happened; the read-outs are what is."""
        status = EditorStatus()
        status.message = 'Saved'
        status.show(title='monaco')
        assert status.message == 'Saved'


class TestWhereItGoes:
    def test_the_track_details_are_one_block_in_a_corner(self) -> None:
        status = EditorStatus()
        assert status.title in list(status.corner.children)
        assert status.corner.anchor == 'top-left'

    def test_the_tool_and_the_message_are_out_of_its_way(self) -> None:
        status = EditorStatus()
        assert status.tool.anchor == 'bottom-left'
        assert status.note.anchor == 'bottom-right'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
