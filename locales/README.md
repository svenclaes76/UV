# Uvalu translations (draft for review)

This folder has 981 user-facing texts from the Uvalu code, translated into Dutch, French, German, Italian and Spanish. There is also an English file for reviewing the English wording. The form of address is informal throughout (je / tu / du / tu / tú), as the spec requires.

Every entry is marked **unreviewed** (fuzzy) until you approve it. Anything you haven't approved shows in English, so nothing unreviewed ever reaches users.

## Files

| File | What it is |
| --- | --- |
| `messages.pot` | English template (the list of all texts) |
| `en/LC_MESSAGES/messages.po` | English, pre-filled with the text from the code. Change the wording here to correct English without touching the code. |
| `nl`, `fr`, `de`, `it`, `es` `/LC_MESSAGES/messages.po` | Draft translations |
| `review.csv` | All languages side by side, with context, for a quick read in Excel (semicolon-separated) |
| `glossary.csv` | Fixed terms and keep-in-English rules |
| `../tools/i18n_compile.py` | Checks placeholders and compiles the `.mo` files (see below) |

## What each entry tells you

In Poedit, the context panel (or in the file itself) shows three things for every entry:

- **Context:** the screen and element the text belongs to, and what it means, e.g. *Portfolio › KPI card label: money invested in open positions*. If a text is used in several places, each extra place gets an **Also:** line.
- **Source reference:** the file and line in the code, e.g. `uvalu/pages_/portfolio.py:280`.
- **Placeholders:** words in `{curly braces}` are filled in by the app. Keep them exactly as they are; you may move them within the sentence.

## How to review (Poedit, free)

1. Open a `.po` file in Poedit.
2. Read the draft next to the English and the context note. Correct it if needed.
3. Turn off **Needs work** to approve the entry. Save.
4. Run `python tools/i18n_compile.py` to check placeholders and build the `.mo` files. Add `--strict` in release CI, so the build fails while anything is still unreviewed.

`pybabel compile` reports false errors on texts containing `%` (such as "BE 30% only"), because Babel mistakes them for %-formatting. Use `tools/i18n_compile.py` instead; Poedit is not affected.

## What is included

| Group | Entries (a few are shared between groups) |
| --- | --- |
| Sign-in, navigation, top bar | 91 |
| Stock preview panel, Analysis page, market names | 93 |
| Dashboard, Help page | 103 |
| Portfolio, Cash activity, shared tables | 151 |
| Dialogs (positions, trades, dividends, cash), sector names | 137 |
| Settings, Watchlist, Screener | 149 |
| Risk page, rebalancing advice, signal explanations, user-facing errors | 200 |
| Planned texts from the spec (Language & region settings, legal links, first-run tour) | 32 |

17 entries have singular/plural forms, and 8 use a message context (`msgctxt`) because the same English word needs two translations, e.g. **Deposit** as a noun (*Storting*) and as a button (*Storten*).

## Deliberately left out

- **Admin portal** (`uvalu/pages_/admin.py`) and admin-only messages in `auth.py`: admin tooling stays English in v1, like the logs. Easy to add later.
- **Log messages and technical error details** (spec L-12).
- **Signal badges** BUY / MONITOR / AVOID / VETO / Strong Buy (spec L-03), tickers, company names, exchange names such as "Euronext Brussels", provider names, browser and OS names.
- **CSS, JavaScript, file names and internal keys.**

## How the code uses these files

The code now wraps every user-facing text: `_()` for plain text, `ngettext()` for plurals, `pgettext()` for the entries with a message context, and `N_()` for texts defined once and translated where they're shown (sector names, dividend frequency, "At Risk", risk labels). Everything goes through `uvalu/i18n.py`; see `docs/i18n-spec.md` §9.

- **Only reviewed entries are used.** The app reads the compiled `.mo` files, which leave out anything still marked *Needs work*, so an unreviewed draft shows in English (and `locales/en` corrections, once approved, replace the English source text).
- **Previewing drafts:** start the app with `UVALU_I18N_DRAFTS=1` to see the unreviewed translations, e.g. for a screenshot pass in German. `UVALU_I18N_PSEUDO=1` shows every text as longer pseudo-text, to spot hard-coded English and clipped labels. Both are ignored when `UVALU_ENV=production`.
- **Try a language without changing your settings:** add `?lang=de` to the URL (session only, never saved).
- **Texts the spec plans but the app doesn't show yet** (legal links, disclaimers, the first-run tour) are kept in `uvalu/i18n_planned.py`, so they stay here for review.

## After changing texts in the code

1. `python tools/i18n_update.py` — extracts the texts from the code into `messages.pot` and merges them into every `.po` file. It keeps every translation, every *Needs work* flag and the Context notes, marks changed texts as needing work (with the old translation as a starting point) and lists what's new or gone. `--check` only reports (CI uses it).
2. Draft the new entries (fuzzy), then review them in Poedit.
3. `python tools/i18n_compile.py` — checks placeholders and markup and builds the `.mo` files. Release CI adds `--strict`.
4. `python tools/i18n_review_csv.py` — rebuilds `review.csv`.

The first run after wiring (Sep 2026) added 42 entries — texts the scan had missed and texts whose wording differs from the proposal (e.g. **Add trade** instead of *Add closed trade*, the new cash-dialog notes) — and moved 16 proposals that no longer match the code to the obsolete section at the end of each file (`#~`). The Excel backup keeps English sheet names: exports beyond number formatting are out of scope in v1 (spec §1).
