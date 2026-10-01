# Uvalu translations

This folder has every user-facing text from the Uvalu code, translated into Dutch, French, German, Italian and Spanish. There is also an English file for correcting the English wording. The form of address is informal throughout (je / tu / du / tu / tú), as the spec requires.

New and changed texts arrive as **unreviewed** (fuzzy) drafts. Anything not yet approved shows in English, and a release can't be tagged while any entry is unreviewed, so nothing unreviewed ever reaches users. See *After changing texts in the code* below for the loop every feature goes through.

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

Percentages: write them the way your language usually does ("30 %" or "30%"). The space before "%" is set at display time to match the region's number format (de-DE "30 %", de-CH "30%"), so text and computed values agree on screen.

`pybabel compile` reports false errors on texts containing `%` (such as "BE 30% only"), because Babel mistakes them for %-formatting. Use `tools/i18n_compile.py` instead; Poedit is not affected.

## What is included

All sign-in, navigation, page, dialog, Settings, Help, Risk and Screener texts, signal explanations, rebalancing advice and user-facing errors, plus the planned texts from the spec (legal links, first-run tour) kept in `uvalu/i18n_planned.py`. `python tools/i18n_update.py --check` prints the current number of entries.

Some entries have singular/plural forms, and a few use a message context (`msgctxt`) because the same English word needs two translations, e.g. **Deposit** as a noun (*Storting*) and as a button (*Storten*).

## Deliberately left out

- **Admin portal** (`uvalu/pages_/admin.py`) and admin-only messages in `auth.py`: admin tooling stays English in v1, like the logs. Easy to add later.
- **Log messages and technical error details** (spec L-12).
- **Signal badges** BUY / MONITOR / AVOID / VETO / Strong Buy (spec L-03), tickers, company names, exchange names such as "Euronext Brussels", provider names, browser and OS names.
- **CSS, JavaScript, file names and internal keys.**

## How the code uses these files

The code wraps every user-facing text: `_()` for plain text, `ngettext()` for plurals, `pgettext()` for the entries with a message context, and `N_()` for texts defined once and translated where they're shown (sector names, dividend frequency, "At Risk", risk labels). Everything goes through `uvalu/i18n.py`; see `docs/i18n-spec.md` §9.

- **Only reviewed entries are used.** The app reads the compiled `.mo` files, which leave out anything still marked *Needs work*, so an unreviewed draft shows in English (and `locales/en` corrections, once approved, replace the English source text).
- **Previewing drafts:** start the app with `UVALU_I18N_DRAFTS=1` to see the unreviewed translations, e.g. for a screenshot pass in German. `UVALU_I18N_PSEUDO=1` shows every text as longer pseudo-text, to spot hard-coded English and clipped labels. Both are ignored when `UVALU_ENV=production`.
- **Try a language without changing your settings:** add `?lang=de` to the URL (session only, never saved).
- **Texts the spec plans but the app doesn't show yet** (legal links, disclaimers, the first-run tour) are kept in `uvalu/i18n_planned.py`, so they stay here for review.

## After changing texts in the code

1. `python tools/i18n_update.py` — extracts the texts from the code into `messages.pot` and merges them into every `.po` file. It keeps every translation, every *Needs work* flag and the Context notes, marks changed texts as needing work (with the old translation as a starting point) and lists what's new or gone. `--check` only reports (CI uses it).
2. Give each new entry a context note — a `# Translators:` comment above the call in the code, or a `Context:` note in `messages.pot` — and run step 1 again. Then draft the new entries (fuzzy) and review them in Poedit before the next release.
3. `python tools/i18n_compile.py` — checks placeholders and markup and builds the `.mo` files. Release CI adds `--strict`.
4. `python tools/i18n_review_csv.py` — rebuilds `review.csv`.
5. `python tools/i18n_update.py --since master` — a Markdown summary (new/removed texts, unreviewed entries per language) to paste into the PR description.

## Merge conflicts

Don't resolve conflicts in this folder by hand, and don't pick one side: that drops the other branch's drafts and reviews. Resolve the code conflicts first, then run `python tools/i18n_merge.py`. It merges every `.po` and `.pot` entry three-way against the common ancestor, reruns steps 1, 3 and 4, and stages `locales/`.

- Added or changed on one side only → that side's version, with its reviewed/unreviewed state.
- Changed differently on both sides → your branch's translation, marked *Needs work*, with the other version in a `# merge: other branch had: …` comment. Pick one in Poedit and approve it.
- `.mo` files and `review.csv` are always rebuilt, never merged (`.gitattributes`).
