# Uvalu translations (draft for review)

This folder has 955 user-facing texts from the Uvalu code, translated into Dutch, French, German, Italian and Spanish. There is also an English file for reviewing the English wording. The form of address is informal throughout (je / tu / du / tu / tú), as the spec requires.

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

## Things to know before wiring this into the code

The code doesn't call a translation function yet, so each English text here is a proposal for the string the code will pass to `_()`. A few were adjusted to make translation possible:

- **Sentences built from pieces were merged**, e.g. the watchlist's "Ticker **{ticker}** not found…" and the invite text "Invited by {inviter} as {role}…". The context note says *merge into one string* where this applies.
- **Hand-made plurals became real plurals**, e.g. `code{s}` → "{count} unused code remaining." / "{count} unused codes remaining." Use `ngettext()` for these.
- **Placeholders got readable names**, e.g. `{amount}`, `{ticker}`, `{date}`, so translators know what goes there.
- **HTML entities were normalised**: `&amp;` is written as `&`. Escape after translating.
- **Values from market data** (sector names, dividend frequency, "At Risk") need translating at display time, not where they are stored.
- **Two sentences insert other translated words**: the value thesis (`{best}` / `{worst}` are sub-score names) and the risk-rating change (`{previous}` → `{rating}`). Pass the translated, lowercase names.

## Coverage

The texts were found by scanning the code automatically and then checked by hand. Once the code uses `_()` and `ngettext()`, run `pybabel extract` and `pybabel update`. That is the definitive list: it merges any text the scan missed and marks proposals that don't match the final code.
