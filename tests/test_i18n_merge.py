"""tools/i18n_merge.py: three-way merge of translation catalogs."""
from babel.messages.catalog import Catalog

from tools.i18n_merge import merge_catalogs


def _cat(entries: dict, template: bool = False) -> Catalog:
    cat = Catalog(locale=None if template else "nl")
    for mid, value in entries.items():
        if template:
            cat.add(mid, auto_comments=list(value))
        else:
            text, fuzzy = value
            cat.add(mid, text, flags={"fuzzy"} if fuzzy else set())
    return cat


def _state(cat: Catalog) -> dict:
    return {m.id: (m.string, m.fuzzy) for m in cat if m.id}


def test_entries_added_on_either_side_are_kept():
    base = _cat({"Save": ("Opslaan", False)})
    ours = _cat({"Save": ("Opslaan", False), "Alpha": ("Alfa", True)})
    theirs = _cat({"Save": ("Opslaan", False), "Beta": ("Bèta", True)})
    merged, conflicts = merge_catalogs(base, ours, theirs)
    assert _state(merged) == {"Save": ("Opslaan", False), "Alpha": ("Alfa", True), "Beta": ("Bèta", True)}
    assert conflicts == []


def test_a_change_on_one_side_wins_including_the_review_flag():
    base = _cat({"Save": ("Bewaar", True), "Close": ("Sluit", True)})
    ours = _cat({"Save": ("Opslaan", False), "Close": ("Sluit", True)})
    theirs = _cat({"Save": ("Bewaar", True), "Close": ("Sluiten", False)})
    merged, conflicts = merge_catalogs(base, ours, theirs)
    assert _state(merged) == {"Save": ("Opslaan", False), "Close": ("Sluiten", False)}
    assert conflicts == []


def test_different_changes_on_both_sides_keep_ours_unreviewed_with_theirs_noted():
    base = _cat({"Dashboard": ("Dashboard", False)})
    ours = _cat({"Dashboard": ("Overzicht", False)})
    theirs = _cat({"Dashboard": ("Startpagina", False)})
    merged, conflicts = merge_catalogs(base, ours, theirs)
    msg = merged.get("Dashboard")
    assert (msg.string, msg.fuzzy) == ("Overzicht", True)
    assert msg.user_comments == ["merge: other branch had: Startpagina"]
    assert conflicts == [(None, "Dashboard")]


def test_same_change_on_both_sides_is_not_a_conflict():
    base = _cat({"Save": ("Bewaar", True)})
    ours = _cat({"Save": ("Opslaan", False)})
    theirs = _cat({"Save": ("Opslaan", False)})
    merged, conflicts = merge_catalogs(base, ours, theirs)
    assert _state(merged) == {"Save": ("Opslaan", False)} and conflicts == []


def test_template_merge_keeps_context_notes_from_both_sides():
    base = _cat({"Close": ["Context: button"]}, template=True)
    ours = _cat({"Close": ["Context: button", "Also: drawer"]}, template=True)
    theirs = _cat({"Close": ["Context: button", "Also: dialog"], "New": ["Context: new"]}, template=True)
    merged, conflicts = merge_catalogs(base, ours, theirs, template=True)
    assert merged.get("Close").auto_comments == ["Context: button", "Also: drawer", "Also: dialog"]
    assert merged.get("New").auto_comments == ["Context: new"]
    assert conflicts == []
