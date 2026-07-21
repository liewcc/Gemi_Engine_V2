"""Offline check for GeminiSequences.get_account_info (no browser needed).

The case that matters is the one that cannot be staged on demand: session cookies
still in the jar while Google has already invalidated them server-side. That state
made get_account_info report a signed-out profile as logged in, and every
attach_file failed behind the false positive. No profile stays dead on request, so
the branch is pinned here instead.

Run:  python check_login_detection.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from providers.gemini.dom import GeminiDOM
from providers.gemini.sequences import GeminiSequences

SIGNIN_MARKER = 'ServiceLogin'
AVATAR_MARKER = 'Google Account'


class _Locator:
    def __init__(self, visible_count):
        self._n = visible_count

    async def count(self):
        return self._n

    def nth(self, i):
        return self

    @property
    def first(self):
        return self

    async def is_visible(self):
        return self._n > 0

    async def evaluate(self, _script):
        return None          # no aria-label to parse; forces the account_id fallback


class _Page:
    """Answers locator() by which marker the selector string contains."""

    def __init__(self, signin, avatar, sidebar):
        self._signin, self._avatar, self._sidebar = signin, avatar, sidebar

    def locator(self, selector):
        if SIGNIN_MARKER in selector:
            return _Locator(1 if self._signin else 0)
        if AVATAR_MARKER in selector:
            return _Locator(1 if self._avatar else 0)
        return _Locator(1 if self._sidebar else 0)   # conversations_list

    async def wait_for_timeout(self, _ms):
        return None

    async def wait_for_load_state(self, _state, timeout=None):
        return None


class _Browser:
    def __init__(self, has_session):
        self._has_session = has_session

    async def cookies(self):
        if not self._has_session:
            return [{'name': 'NID', 'domain': '.google.com'}]
        return [{'name': '__Secure-1PSID', 'domain': '.google.com'}]


class _Engine:
    is_running = True
    active_profile = 'Profile 17'

    def __init__(self, has_session, signin, avatar, sidebar):
        self._browser = _Browser(has_session)
        self._page = _Page(signin, avatar, sidebar)

    def _load_profile_cache(self):
        return {'Profile 17': {'user_name': 'rocket.slasher@gmail.com'}}


def _verdict(has_session, signin, avatar, sidebar=False):
    seq = GeminiSequences.__new__(GeminiSequences)
    seq._e = _Engine(has_session, signin, avatar, sidebar)
    # Real DOM object: the sidebar selector must be the one shipping in dom.py,
    # so a rename there surfaces here instead of silently passing.
    seq._dom = GeminiDOM()
    assert SIGNIN_MARKER not in seq._dom.conversations_list(), (
        "sidebar selector now collides with the sign-in marker; this stub is lying"
    )
    return asyncio.new_event_loop().run_until_complete(seq.get_account_info())


def _run():
    # The regression this file exists for: cookies survive, Google says no.
    r = _verdict(has_session=True, signin=True, avatar=False)
    assert r['logged_in'] is False, (
        "stale session cookies must not count as proof of login"
    )

    # The signed-out Gemini landing page renders BOTH a sign-in link and an
    # avatar element. Reading the avatar first is what let a dead session pass.
    r = _verdict(has_session=True, signin=True, avatar=True)
    assert r['logged_in'] is False, (
        "a visible sign-in control must outrank a visible avatar"
    )

    # No session cookie at all is conclusive on its own.
    r = _verdict(has_session=False, signin=False, avatar=True)
    assert r['logged_in'] is False, "no session cookie means no session"

    # Genuinely logged in: avatar, no sign-in control.
    r = _verdict(has_session=True, signin=False, avatar=True)
    assert r['logged_in'] is True, "a real login must still be detected"
    assert r['account_id'] == 'rocket.slasher@gmail.com', (
        "cached profile metadata should name a DOM-confirmed login"
    )

    # Neither indicator rendered yet; the sidebar only exists for a live session.
    r = _verdict(has_session=True, signin=False, avatar=False, sidebar=True)
    assert r['logged_in'] is True, "sidebar is a valid positive when both flags miss"

    r = _verdict(has_session=True, signin=False, avatar=False, sidebar=False)
    assert r['logged_in'] is False and r['status'] == 'unknown', (
        "no signal at all must not be reported as logged in"
    )

    print("[OK] get_account_info login detection passed")


if __name__ == '__main__':
    _run()
