"""Registry of st.Page objects.

app.py builds the pages (it needs each module's render callable) and populates
``pages`` here at startup. Page modules that link to sibling pages read from
this registry at render time, avoiding an import cycle with app.py.
"""

pages: dict = {}  # name -> st.Page, populated by app.py before _nav.run()
