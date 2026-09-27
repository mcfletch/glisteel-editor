"""The art four tracks share, written once instead of four times.

`trees/` and `gantry/` are byte-identical across every track baked from the
shipped art: 25.5 MB of bark, branch and impostor maps that say nothing about
which circuit is being driven. Written into each track they are 25.5 MB per
track in a release; written once they are 25.5 MB in it.

The split needs no path to change. A track pack and its art pack unpack into the
same directory, so `trees/...` in a tile resolves exactly as it does in a bake
that never split.
"""

import contextlib
import os

import pytest
from OpenGLContext import atomicfiles

from glisteel_editor import bake


def baked(where, subdirectories=('trees', 'gantry', 'signs'), body=b'art'):
    """A directory shaped like a bake, without the cost of baking one."""
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, 'tileset.json'), 'w') as handle:
        handle.write('{}')
    for name in subdirectories:
        inside = os.path.join(where, name)
        os.makedirs(inside, exist_ok=True)
        with open(os.path.join(inside, '%s.png' % name), 'wb') as handle:
            handle.write(body)
    return where


class TestWhatIsTakenOutOfATrack:
    def test_the_shared_art_moves_to_the_pack(self, tmp_path) -> None:
        track = baked(str(tmp_path / 'track'))
        art = str(tmp_path / 'art')
        bake.split_art(track, art)
        for name in bake.SHARED_ART:
            assert os.path.isfile(os.path.join(art, name, '%s.png' % name))
            assert not os.path.exists(os.path.join(track, name))

    def test_what_is_this_track_stays_in_it(self, tmp_path) -> None:
        """`signs/` carries this circuit's own posted limits."""
        track = baked(str(tmp_path / 'track'))
        bake.split_art(track, str(tmp_path / 'art'))
        assert os.path.isfile(os.path.join(track, 'signs', 'signs.png'))
        assert os.path.isfile(os.path.join(track, 'tileset.json'))
        assert not os.path.exists(os.path.join(tmp_path, 'art', 'signs'))

    def test_it_says_what_it_moved(self, tmp_path) -> None:
        track = baked(str(tmp_path / 'track'))
        moved = bake.split_art(track, str(tmp_path / 'art'))
        assert sorted(moved) == sorted(bake.SHARED_ART)

    def test_a_bake_with_none_of_it_is_not_an_error(self, tmp_path) -> None:
        """`--forest tiles` grows the trees into the tiles and writes no art."""
        track = baked(str(tmp_path / 'track'), subdirectories=('signs',))
        assert bake.split_art(track, str(tmp_path / 'art')) == []


class TestASecondTrackIntoTheSamePack:
    def test_art_already_there_is_not_written_twice(self, tmp_path) -> None:
        art = str(tmp_path / 'art')
        first = baked(str(tmp_path / 'first'))
        bake.split_art(first, art)
        second = baked(str(tmp_path / 'second'))
        assert bake.split_art(second, art) == []
        for name in bake.SHARED_ART:
            assert not os.path.exists(os.path.join(second, name))

    def test_art_that_differs_is_refused_rather_than_dropped(self,
                                                             tmp_path) -> None:
        """The whole split rests on the art being the same art.

        Silently keeping the first copy would put one track's art under another
        track's tiles the day that stops being true, and nothing would say so.
        """
        art = str(tmp_path / 'art')
        bake.split_art(baked(str(tmp_path / 'first')), art)
        second = baked(str(tmp_path / 'second'), body=b'different')
        with pytest.raises(bake.ArtDiffers) as raised:
            bake.split_art(second, art)
        assert 'trees' in str(raised.value)

    def test_the_track_is_left_alone_when_it_is_refused(self, tmp_path) -> None:
        art = str(tmp_path / 'art')
        bake.split_art(baked(str(tmp_path / 'first')), art)
        second = baked(str(tmp_path / 'second'), body=b'different')
        with pytest.raises(bake.ArtDiffers):
            bake.split_art(second, art)
        assert os.path.isfile(os.path.join(second, 'trees', 'trees.png'))


class TestFromTheCommandLine:
    def test_the_option_is_offered(self) -> None:
        options = bake.build_parser().parse_args(['--art-pack', '/tmp/art'])
        assert options.art_pack == '/tmp/art'

    def test_a_bake_without_it_keeps_its_art(self) -> None:
        assert bake.build_parser().parse_args([]).art_pack is None


class TestTwoTracksSplittingAtOnce:
    def test_each_directory_is_checked_and_staged_under_its_lock(self, tmp_path,
                                                                 monkeypatch) -> None:
        """Two bakes writing one pack in parallel would otherwise both find a
        directory missing and both stage it."""
        events = []
        staged = atomicfiles.staged_directory

        @contextlib.contextmanager
        def lock(path):
            events.append(('lock', os.path.basename(path)))
            yield
            events.append(('unlock', os.path.basename(path)))

        @contextlib.contextmanager
        def staging(path):
            events.append(('stage', os.path.basename(path)))
            with staged(path) as where:
                yield where

        monkeypatch.setattr(atomicfiles, 'file_lock', lock)
        monkeypatch.setattr(atomicfiles, 'staged_directory', staging)
        bake.split_art(baked(str(tmp_path / 'track')), str(tmp_path / 'art'))
        for name in bake.SHARED_ART:
            at = events.index(('stage', name))
            assert events[at - 1] == ('lock', '.%s.lock' % name)
            assert events[at + 1] == ('unlock', '.%s.lock' % name)
