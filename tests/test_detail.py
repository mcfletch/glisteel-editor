"""How much ground the plan view meshes, and how finely.

The landscape is kilometres across and the screen is a thousand pixels: meshing
all of it at one resolution means the detail is wrong at every zoom but one --
too coarse to see a river bed when you are close, and more triangles than
pixels when you are not. So the ground that is meshed is the ground being
looked at, at the detail the screen can actually show.

Pure arithmetic on a rectangle and a scale.
"""
import pytest

from glisteel_editor.detail import GroundPatch, patch_for

VIEWPORT = (1200, 800)
EXTENT = 4096.0


def _patch(centre=(0.0, 0.0), span=EXTENT, **named):
    named.setdefault('viewport', VIEWPORT)
    named.setdefault('extent', EXTENT)
    return patch_for(centre, span, **named)


class TestWhatIsMeshed:
    def test_zoomed_out_it_is_the_whole_landscape(self) -> None:
        patch = _patch()
        assert patch.minimum[0] <= -EXTENT / 2.0
        assert patch.maximum[0] >= EXTENT / 2.0

    def test_zoomed_in_it_is_a_small_part_of_it(self) -> None:
        patch = _patch(span=200.0)
        assert patch.maximum[0] - patch.minimum[0] < EXTENT / 2.0

    def test_it_is_bigger_than_what_is_on_screen(self) -> None:
        """So a small pan does not re-mesh the landscape."""
        patch = _patch(span=200.0)
        assert patch.maximum[0] - patch.minimum[0] > 200.0

    def test_it_never_reaches_outside_the_landscape(self) -> None:
        patch = _patch(centre=(EXTENT / 2.0, EXTENT / 2.0), span=400.0)
        assert patch.maximum[0] <= EXTENT / 2.0 + 1e-6
        assert patch.maximum[1] <= EXTENT / 2.0 + 1e-6

    def test_it_is_centred_on_what_is_being_looked_at(self) -> None:
        patch = _patch(centre=(300.0, -700.0), span=200.0)
        middle_x = (patch.minimum[0] + patch.maximum[0]) / 2.0
        middle_z = (patch.minimum[1] + patch.maximum[1]) / 2.0
        assert (middle_x, middle_z) == pytest.approx((300.0, -700.0))

    def test_it_is_square(self) -> None:
        """The map turns and the window resizes; a square patch survives both."""
        patch = _patch(span=500.0)
        assert (patch.maximum[0] - patch.minimum[0]) \
            == pytest.approx(patch.maximum[1] - patch.minimum[1])


class TestHowFinely:
    def test_closer_in_means_finer_ground(self) -> None:
        """The whole point: the detail follows the zoom."""
        near = _patch(span=200.0)
        far = _patch(span=EXTENT)
        assert near.spacing() < far.spacing() / 4.0

    def test_it_never_costs_more_than_its_budget(self) -> None:
        for span in (10.0, 100.0, 1000.0, EXTENT):
            assert _patch(span=span).resolution <= GroundPatch.FINEST

    def test_it_never_drops_below_a_floor(self) -> None:
        """A patch of four vertices is not ground."""
        assert _patch(span=EXTENT * 4).resolution >= GroundPatch.COARSEST

    def test_a_bigger_window_asks_for_more(self) -> None:
        small = _patch(span=500.0, viewport=(400, 300))
        large = _patch(span=500.0, viewport=(2400, 1800))
        assert large.resolution >= small.resolution

    def test_close_in_the_samples_are_metres_apart_not_tens(self) -> None:
        """Which is what a river bed twelve metres across needs."""
        assert _patch(span=200.0).spacing() < 5.0


class TestWhenToDoItAgain:
    def test_the_same_view_wants_the_same_patch(self) -> None:
        patch = _patch(span=400.0)
        assert patch.serves((0.0, 0.0), 400.0, VIEWPORT, EXTENT)

    def test_a_small_pan_is_still_served(self) -> None:
        patch = _patch(span=400.0)
        assert patch.serves((20.0, 20.0), 400.0, VIEWPORT, EXTENT)

    def test_panning_off_the_edge_of_it_is_not(self) -> None:
        patch = _patch(span=400.0)
        assert not patch.serves((3000.0, 0.0), 400.0, VIEWPORT, EXTENT)

    def test_a_small_zoom_is_still_served(self) -> None:
        """Or every wheel notch re-meshes the landscape."""
        patch = _patch(span=400.0)
        assert patch.serves((0.0, 0.0), 380.0, VIEWPORT, EXTENT)

    def test_zooming_right_in_is_not(self) -> None:
        patch = _patch(span=400.0)
        assert not patch.serves((0.0, 0.0), 40.0, VIEWPORT, EXTENT)

    def test_zooming_right_out_is_not(self) -> None:
        patch = _patch(span=400.0)
        assert not patch.serves((0.0, 0.0), 4000.0, VIEWPORT, EXTENT)

    def test_a_patch_covering_the_whole_landscape_serves_a_zoom_out(self) -> None:
        """There is nothing coarser to go to, so it must not thrash."""
        patch = _patch(span=EXTENT)
        assert patch.serves((0.0, 0.0), EXTENT * 3, VIEWPORT, EXTENT)
