"""Registry of st.Page objects.

app.py builds the pages (it needs each module's render callable) and populates
``pages`` here at startup. Page modules that link to sibling pages read from
this registry at render time, avoiding an import cycle with app.py.

It also keeps a two-step page history per session (``record_visit`` /
``back_target``), so the Legal and Settings pages' "← Back" returns to the
page the user came from instead of always to the Dashboard.
"""

pages: dict = {}  # name -> st.Page, populated by app.py before _nav.run()

_LAST, _PREV = "_uv_last_page", "_uv_prev_page"
_NO_BACK = ("admin",)   # its own shell; never a "back" destination


def record_visit(key: "str | None") -> None:
    """Called by app.py on every run with the current page's registry key.
    Reruns of the same page don't shift the history."""
    import streamlit as st
    if not key or key in _NO_BACK:
        return
    last = st.session_state.get(_LAST)
    if key != last:
        st.session_state[_PREV] = last
        st.session_state[_LAST] = key


def back_target(current: str):
    """(page, key) to go back to from ``current``: the most recent other page
    this session, the Dashboard otherwise (a full reload starts a new
    session). (None, None) when not even the Dashboard is registered."""
    import streamlit as st
    last, prev = st.session_state.get(_LAST), st.session_state.get(_PREV)
    key = prev if last == current else last
    if not key or key == current or key not in pages:
        key = "dashboard"
    return pages.get(key), (key if key in pages else None)
