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

        # Config number free -> untouched, never mind what else is in the folder.
        assert resolve_next_number(d, '', 2, 6, True) == 6
        assert resolve_next_number(d, '', 2, 6, False) == 6

        # Config number taken. ON fills the gap, OFF appends past the highest.
        assert resolve_next_number(d, '', 2, 1, True) == 4
        assert resolve_next_number(d, '', 2, 1, False) == 6

        # Neither mode may ever return an occupied number.
        for gap_fill in (True, False):
            for start in range(1, 8):
                got = resolve_next_number(d, '', 2, start, gap_fill)
                assert not os.path.exists(os.path.join(d, f"{got:02d}.png")), (start, gap_fill, got)

        # Prefix isolation: files of another prefix must not shift this series.
        touch('other_09.png')
        assert resolve_next_number(d, 'other_', 2, 9, False) == 10
        assert resolve_next_number(d, '', 2, 1, False) == 6

        # A non-conforming name (e.g. manually renamed 04 -> 04x) stays ignored.
        touch('04x.png')
        assert resolve_next_number(d, '', 2, 1, True) == 4

    print("check_next_number: OK")


if __name__ == '__main__':
    _run()
