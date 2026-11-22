"""Small deployment controls. These are per-session guards, not global limits."""
import os
import time
from support import SupportError


def get_setting(streamlit, name, default):
    if name in os.environ:
        return os.environ[name]
    try:
        return streamlit.secrets.get(name, default)
    except FileNotFoundError:
        return default


def guard_live(session, enabled, now=None):
    if not enabled:
        raise SupportError("Live evaluation is disabled on this deployment.")
    now = time.monotonic() if now is None else now
    count = session.get("live_attempts", 0)
    if count >= 10:
        raise SupportError("This session reached its 10 live-attempt limit. Ask the instructor before starting another session.")
    previous = session.get("last_live_attempt")
    if previous is not None and now - previous < 5:
        raise SupportError("Wait at least five seconds between live attempts.")
    session["last_live_attempt"] = now
    session["live_attempts"] = count + 1
