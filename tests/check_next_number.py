"""Offline check for resolve_next_number (no browser needed).

Run:  python check_next_number.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from providers.gemini.sequences import resolve_next_number


def _run():
    with tempfile.TemporaryDirectory() as d:
        def touch(name):
            open(os.path.join(d, name), 'w').close()

        # Empty folder: the config number is used as-is, both modes.
        assert resolve_next_number(d, '', 2, 7, True) == 7
        assert resolve_next_number(d, '', 2, 7, False) == 7

        for n in (1, 2, 3, 5):  # 4 is a deliberate gap
            touch(f"{n:02d}.png")

        # ON always appends after the highest, even when start is free, so a
        # stale config number self-heals and gaps are never reused.
        assert resolve_next_number(d, '', 2, 1, True) == 6
        assert resolve_next_number(d, '', 2, 4, True) == 6
        assert resolve_next_number(d, '', 2, 9, True) == 9  # start wins when ahead

        # OFF uses start as given; a collision falls back to the same append.
        assert resolve_next_number(d, '', 2, 4, False) == 4
        assert resolve_next_number(d, '', 2, 1, False) == 6

        # Neither mode may return an occupied number, or reuse the gap at 4
        # unless the caller asked for exactly that number with tracking off.
        for track_last in (True, False):
            for start in range(1, 8):
                got = resolve_next_number(d, '', 2, start, track_last)
                assert not os.path.exists(os.path.join(d, f"{got:02d}.png")), (start, track_last, got)
                if track_last:
                    assert got >= 6, (start, got)

        # Prefix isolation: files of another prefix must not shift this series.
        touch('other_09.png')
        assert resolve_next_number(d, 'other_', 2, 1, True) == 10
        assert resolve_next_number(d, '', 2, 1, True) == 6

        # A non-conforming name (e.g. manually renamed 06 -> 06x) is ignored by
        # the scan, but a real collision on the resolved name is still stepped over.
        touch('06.png')
        touch('07x.png')
        assert resolve_next_number(d, '', 2, 1, True) == 7

    print("check_next_number: OK")


if __name__ == '__main__':
    _run()
