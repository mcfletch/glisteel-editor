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


class TestWhatTheLineCosts:
    """A designer reading "4.09 km" learns nothing about the third of it that
    is a viaduct. The read-out says what is on the line as well as how long it
    is."""

    def _status(self):
        from glisteel_editor.status import EditorStatus
        return EditorStatus()

    def test_a_plain_road_says_only_its_length(self) -> None:
        status = self._status()
        status.show(title='t', points=4, length=1200.0, scale=2.0)
        assert status.route.value == '4 points, 1.20 km'

    def test_structures_are_named_and_counted(self) -> None:
        status = self._status()
        status.show(title='t', points=4, length=1200.0, scale=2.0,
                    structures={'bridge': 2, 'tunnel': 1})
        assert '2 bridges' in status.route.value
        assert '1 tunnel' in status.route.value

    def test_one_of_a_kind_is_singular(self) -> None:
        status = self._status()
        status.show(title='t', points=4, length=1200.0, scale=2.0,
                    structures={'bridge': 1})
        assert '1 bridge,' in status.route.value + ','
        assert 'bridges' not in status.route.value

    def test_a_causeway_is_spelt_properly_in_the_plural(self) -> None:
        status = self._status()
        status.show(title='t', points=4, length=1200.0, scale=2.0,
                    structures={'causeway': 3})
        assert '3 causeways' in status.route.value

    def test_they_come_out_in_a_settled_order(self) -> None:
        """Two counts that swap places every rebuild are a flickering label."""
        status = self._status()
        first = {'tunnel': 1, 'bridge': 2}
        second = {'bridge': 2, 'tunnel': 1}
        status.show(title='t', points=4, length=1.0, scale=1.0,
                    structures=first)
        one = status.route.value
        status.show(title='t', points=4, length=1.0, scale=1.0,
                    structures=second)
        assert status.route.value == one
