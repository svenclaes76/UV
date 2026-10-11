## Summary

<!-- What changes for the user or operator, and why. -->

## Changes

-

## Translations

<!-- Paste the output of: python tools/i18n_update.py --since master
     Every new text needs a context note and drafts in all languages (fuzzy is fine);
     unreviewed entries must be approved before the next release is tagged.
     Write "No UI text changed" if the summary shows 0 new, 0 removed. -->

## Checks

- [ ] Tests pass locally (`python -m pytest`)
- [ ] `python tools/i18n_update.py --check` and `python tools/i18n_compile.py` pass
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (full detail); version impact: MAJOR / MINOR / PATCH
- [ ] `RELEASE_NOTES.md` updated under `[Unreleased]` (what subscribers notice, benefit first), or nothing subscribers would notice
