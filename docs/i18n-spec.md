# Uvalu — Multi-language & Locale Support Requirements

Sep 27, 2026 · Sven Claes · v1

> Source of truth for the i18n work on branch `feature/i18n-locales`. Draft translations live in `locales/` (see `locales/README.md`). The repo notes at the end map this spec onto the actual code.

## 1. Purpose and scope

Uvalu v1 will ship with a fully translated interface in six languages and locale-correct formatting for numbers, currencies, dates and percentages. Users choose both from the Settings menu.

**Goals**

- Every user-facing string in the app is available in all six languages.
- Financial figures always display in the user's chosen regional format. They never mix formats on one screen.
- Language and region are separate settings. A Belgian user can read the app in English while seeing 1.234,56 € formatting.
- Adding a seventh language later requires only new translation files, with no code changes.

**In scope for v1**

- UI text, including navigation, labels, buttons, tooltips, errors, empty states and signal badge tooltips.
- Locale formatting for all numeric, monetary and date values.
- Settings for language, region format, display currency and date format.
- Detecting defaults on first visit and persisting the user's choices.
- Legal texts: privacy policy, terms of use and investment disclaimer (L-11).
- In-app help and onboarding: tooltips, model explanations and the first-run tour (L-13).
- Locale-aware sorting and accent-insensitive search (F-13, F-14).

**Out of scope for v1** (see section 13)

- Translating market data from providers, such as company names, descriptions and news.
- Right-to-left languages.
- Translated emails, PDFs and exports beyond number formatting.

## 2. Supported languages and locales

Uvalu v1 supports six interface languages, each with one default region and a short list of supported regions. English is the source language, and all other languages are translated from it.

| Language | Code | Native name in picker | Default region | Other supported regions (v1) |
| --- | --- | --- | --- | --- |
| English | en | English | en-GB | en-IE, en-US |
| Dutch | nl | Nederlands | nl-BE | nl-NL |
| French | fr | Français | fr-BE | fr-FR, fr-LU, fr-CH |
| German | de | Deutsch | de-DE | de-BE, de-AT, de-LU, de-CH |
| Italian | it | Italiano | it-IT | it-CH |
| Spanish | es | Español | es-ES | — |

**Reference formats for the default regions** (from CLDR, via Babel):

| Locale | Number | Currency (EUR) | Short date | Medium date |
| --- | --- | --- | --- | --- |
| en-GB | 1,234.56 | €1,234.56 | 27/09/2026 | 27 Sept 2026 |
| nl-BE | 1.234,56 | € 1.234,56 | 27/09/2026 | 27 sep 2026 |
| fr-BE | 1 234,56 | 1 234,56 € | 27/09/26 | 27 sept. 2026 |
| de-DE | 1.234,56 | 1.234,56 € | 27.09.26 | 27.09.2026 |
| it-IT | 1.234,56 | 1.234,56 € | 27/09/26 | 27 set 2026 |
| es-ES | 1.234,56 | 1.234,56 € | 27/9/26 | 27 sept 2026 |
| de-CH | 1’234.56 | EUR 1’234.56 | 27.09.26 | 27.09.2026 |

The app shows exactly what the locale library produces. The values above are illustrations and should never be hard-coded. Tests must also cover several edge cases: Swiss locales use an apostrophe as the thousands separator, French uses a narrow no-break space, and some CLDR versions leave out the Spanish thousands separator for 4-digit numbers.

## 3. Definitions

| Term | Meaning in this spec |
| --- | --- |
| Interface language | The language of UI text (en, nl, fr, de, it, es). |
| Region format | The locale used to format numbers, dates and currency amounts, such as nl-BE or de-CH. It is independent of the interface language. |
| Display currency | The currency used to show portfolio totals and aggregates. |
| Instrument currency | The currency an instrument trades in, such as USD for AAPL. It is always shown as-is at the instrument level. |
| Fallback | The string or format used when a translation or locale is missing. |
| Message ID | The stable English source string, or key, that identifies a translatable text. |

## 4. Functional requirements — UI text

All user-facing text is externalised and rendered in the active interface language. The first release ships with 100% coverage in all six languages.

| ID | Requirement | Priority |
| --- | --- | --- |
| L-01 | Every user-facing string goes through the translation function. No literal UI text appears in page code. | Must |
| L-02 | Coverage includes navigation, page titles, labels, buttons, tooltips, help text, validation and error messages, empty states, toasts, chart titles, axis labels and legends. | Must |
| L-03 | Signal badges (BUY / MONITOR / AVOID / VETO) stay in English in every language as a brand element. Their tooltips and explanations are translated. | Must |
| L-04 | Plurals use locale plural rules, for example "1 position" and "3 positions", rather than string concatenation. | Must |
| L-05 | Sentences with variables use named placeholders, such as `{ticker} is {pct} below fair value`, so translators can reorder words. | Must |
| L-06 | Changing the language re-renders the current page immediately, keeps the user on the same screen, and keeps filters and selections. | Must |
| L-07 | Layouts tolerate text about 35% longer than English (German and French run longest). Buttons and badges must not clip or wrap badly. | Must |
| L-08 | Model names and abbreviations such as DCF, EV/EBITDA, EPV, VaR, CVaR and HHI stay untranslated. Their tooltip explanations are translated. | Should |
| L-09 | Tickers, ISINs, exchange codes and company names from data providers are never translated. | Must |
| L-10 | The browser tab title and the `lang` attribute of the page reflect the active language. | Should |
| L-11 | The privacy policy, terms of use and investment disclaimer are available in all six languages. The user sees them in the active interface language, including at sign-up. Each translation carries a version number and date, and the English version is the reference if versions conflict. | Must |
| L-12 | Log messages, audit events and technical error details stay in English, per the logging spec. Only the user-facing message shown next to an error is translated. | Must |
| L-13 | In-app help is translated in v1: tooltips, model explanations (DCF, Graham Number, EV/EBITDA, EPV, dividend models, VaR) and the first-run tour. Long-form documentation is deferred (section 13). | Must |

## 5. Functional requirements — numbers, currency and dates

The region format setting controls all formatting. The interface language never does. Formatting happens only at display time, and stored values stay locale-neutral: numbers as floats or decimals, dates in ISO 8601 UTC.

| ID | Requirement | Priority |
| --- | --- | --- |
| F-01 | Decimal and thousands separators follow the region format everywhere: tables, metric cards, charts, tooltips and exports. | Must |
| F-02 | Currency amounts use the locale's symbol position and spacing, such as € 1.234,56 or 1.234,56 €. | Must |
| F-03 | Instrument-level values (price, fair value, target) show in the instrument currency. Portfolio totals show in the display currency. | Must |
| F-04 | Converted amounts are clearly marked, for example with a ≈ prefix or a "converted at" tooltip showing the FX rate and date. | Should |
| F-05 | Percentages use locale formatting (12,5 % in fr/de, 12.5% in en). Signed values always show the sign: +3,2 % or −1,4 %. | Must |
| F-06 | Large numbers can use compact notation per locale (1,2 Mrd. in German, 1.2B in English) where space is tight, such as market-cap cards. | Should |
| F-07 | Dates use the chosen date style: short, medium or ISO (2026-09-27). Month and day names come from the locale. | Must |
| F-08 | Chart axes, tick labels and hover tooltips (Plotly/Altair) use the same separators and date formats as the rest of the app. | Must |
| F-09 | The number of decimals is set per value type rather than per locale: prices 2 (or instrument precision), percentages 1–2, ratios 2, share quantities up to 4. | Must |
| F-10 | Number inputs are parsed using the region format, so 1.234 means 1234 in nl-BE and 1.234 in en-GB. The parsed value is shown back before saving, and input that fails to parse is rejected with a message rather than guessed. | Must |
| F-11 | CSV exports offer two options: locale format (for Excel in that region, with `;` delimiter in comma-decimal locales) or machine format (dot decimal, ISO dates, `,` delimiter). | Should |
| F-12 | Times display in the user's time zone, with Europe/Brussels as the default. Market close times keep the exchange's own time zone with a label. | Should |
| F-13 | Text columns (company names, sectors, countries) sort by the rules of the active language, so accented names like Électricité or Ørsted sit with E and O rather than at the end. Use a Unicode collation library such as `pyuca`, not plain string sorting. | Must |
| F-14 | Search in the Screener and elsewhere ignores accents and case: "societe" finds "Société Générale" and "loreal" finds "L'Oréal". Punctuation such as apostrophes and hyphens is ignored when matching. | Must |

## 6. Defaults, detection and fallback

An explicit user choice always wins. Detection only sets the first-visit default, and anything missing falls back to English with en-GB formatting.

**Interface language, first match wins:**

1. The saved user profile setting (signed-in users).
2. A `?lang=` URL parameter, which is useful for support links and testing. It applies to the session only and is never saved automatically.
3. The browser `Accept-Language` header, matched to the nearest supported language. For example, nl-NL becomes nl, de-AT becomes de, and pt-PT falls through.
4. The system default from the config file, which is `en`.

**Region format, first match wins:**

1. The saved user profile setting.
2. The full browser locale if it is supported (fr-BE maps to fr-BE, de-AT to de-AT).
3. The default region of the chosen language (section 2).

**Fallback rules**

| ID | Requirement | Priority |
| --- | --- | --- |
| D-01 | A missing translation for one string shows the English source string rather than the message ID or a blank. | Must |
| D-02 | Each missing translation is logged once per session at WARNING level, following the logging spec, with language and message ID. | Should |
| D-03 | An unsupported or corrupt saved locale value resets to the default and does not raise an error. | Must |
| D-04 | Regional language variants (for example nl-BE wording versus nl-NL wording) fall back to the base language file. Only the differing strings go in a regional file. | Could |

## 7. Settings menu — Language & region

Settings gets a dedicated **Language & region** page with six user-level settings. Changes apply instantly with no Save button, and each one shows a live preview. A system-level config file sets the defaults and which languages are enabled.

### 7.1 User settings

| Setting | Control | Options | Default | Notes |
| --- | --- | --- | --- | --- |
| Language | Dropdown | English, Nederlands, Français, Deutsch, Italiano, Español | Detected (section 6) | Each option is shown in its own language, regardless of the current UI language. |
| Region format | Dropdown, grouped by language | Locales from section 2, such as "België (Nederlands) — 1.234,56" | Language's default region | An option "Same as language" is at the top. |
| Display currency | Dropdown | EUR, USD, GBP, CHF | CHF for de-CH, fr-CH and it-CH; EUR for all other regions | Applies to portfolio totals only (F-03). The default follows the region until the user picks a currency explicitly. |
| Date format | Radio | Short (27/09/2026), Medium (27 sep 2026), ISO (2026-09-27) | Short | Examples render in the selected region. |
| Time zone | Searchable dropdown | IANA zones | Europe/Brussels | Used for timestamps and "last updated". |
| First day of week | Radio | Monday, Sunday | From region (Monday for EU) | Used for date pickers and calendar views. |

### 7.2 Behaviour

| ID | Requirement | Priority |
| --- | --- | --- |
| S-01 | A preview panel shows a sample price, a portfolio total, a percentage change, a date and a BUY badge, rendered with the current selection. | Must |
| S-02 | Changing any setting applies to the whole app immediately, without logging out or a manual refresh. | Must |
| S-03 | Settings are saved to the user profile and follow the user across devices. | Must |
| S-04 | Before sign-in, including on the login page, a compact language switcher is available in the header or footer. The choice is kept in the session and saved to the profile at sign-in if none is set. | Must |
| S-05 | A "Reset to defaults" action restores detected and system defaults after a confirmation. | Should |
| S-06 | The language dropdown is always reachable within two clicks, and its label keeps a universal icon (globe) so a user who picked the wrong language can find it. | Must |
| S-07 | Every settings change is logged at INFO level as an audit event with old and new values, following the logging spec. | Should |
| S-08 | Settings pages and the preview are fully translated, including the region option names. | Must |

### 7.3 System configuration (admin, config file)

The settings below live in the system config file, in line with the logging spec's config-file approach. There is no admin UI in v1.

```yaml
i18n:
  default_language: en
  enabled_languages: [en, nl, fr, de, it, es]
  default_region: en-GB
  enabled_regions: [en-GB, en-IE, en-US, nl-BE, nl-NL, fr-BE, fr-FR, fr-LU, fr-CH, de-DE, de-BE, de-AT, de-LU, de-CH, it-IT, it-CH, es-ES]
  default_display_currency: EUR
  display_currency_by_region:
    de-CH: CHF
    fr-CH: CHF
    it-CH: CHF
  enabled_display_currencies: [EUR, USD, GBP, CHF]
  default_time_zone: Europe/Brussels
  allow_url_lang_param: true
  log_missing_translations: true
```

| ID | Requirement | Priority |
| --- | --- | --- |
| C-01 | Removing a language from `enabled_languages` hides it from the pickers. Users who had it selected fall back to `default_language` and see a one-time notice. | Must |
| C-02 | An invalid config value blocks startup with a clear error message naming the key. The app never starts with a broken locale setup. | Must |
| C-03 | Config changes take effect on restart. Hot reload is not required in v1. | Must |

## 8. Financial terminology and content rules

A controlled glossary fixes how core financial terms are translated, so the same concept always gets the same word. The full, current glossary is `locales/glossary.csv`; the table below is the core set.

### 8.1 Glossary

Signal badges (BUY, MONITOR, AVOID, VETO) are not in the glossary because they stay in English (section 14).

| English | Dutch | French | German | Italian | Spanish |
| --- | --- | --- | --- | --- | --- |
| Fair value | Intrinsieke waarde | Juste valeur | Fairer Wert | Valore equo | Valor razonable |
| Margin of safety | Veiligheidsmarge | Marge de sécurité | Sicherheitsmarge | Margine di sicurezza | Margen de seguridad |
| Portfolio | Portefeuille | Portefeuille | Portfolio | Portafoglio | Cartera |
| Position | Positie | Position | Position | Posizione | Posición |
| Dividend | Dividend | Dividende | Dividende | Dividendo | Dividendo |
| Unrealised P&L (short) | Niet-gerealiseerde W/V | P/V latente | Unrealisierter G/V | P/L non realizzato | G/P no realizada |
| Composite score | Totaalscore | Score composite | Gesamtscore | Punteggio composito | Puntuación compuesta |
| Screener | Screener | Screener | Screener | Screener | Screener |

### 8.2 Content rules

| ID | Requirement | Priority |
| --- | --- | --- |
| G-01 | The glossary is kept as a versioned file in the repo, one row per term. Translators must use it. | Must |
| G-02 | Badge labels are the same English words in every language, so badges keep a fixed width. Their translated tooltips have no length limit. | Should |
| G-03 | Disclaimers ("not investment advice", risk warnings) and legal texts are never machine-only. They are reviewed line by line against the English reference before release (W-05). | Must |
| G-04 | Tone is professional and direct. Uvalu uses the informal form of address consistently in every language: je (nl), du (de), tu (fr), tu (it), tú (es). Informal never means chatty: no jokes or emoji, and disclaimers and risk warnings stay factual. Copy avoids direct address where a neutral label works. | Should |
| G-05 | Anglicisms that local investors commonly use (screener, ETF, cash flow) may stay in English when the glossary says so. | Could |

## 9. Technical architecture

The stack is gettext for strings and Babel (CLDR) for formatting, both wrapped in one `uvalu/i18n.py` module that all pages import. Pages never call gettext or Babel directly.

### 9.1 Components

| Component | Responsibility |
| --- | --- |
| `uvalu/i18n.py` | Resolves the active language and region from `st.session_state`. Exposes `_()`, `ngettext()`, `pgettext()`, `fmt_num()`, `fmt_money()`, `fmt_pct()`, `fmt_date()`, `fmt_compact()` and `parse_num()`. |
| `locales/<lang>/LC_MESSAGES/messages.po` | Translations per language, including `en`. They are compiled to `.mo` at build time. |
| `locales/messages.pot` | The template extracted from code with `pybabel extract`. |
| `locales/glossary.csv` | The financial glossary (section 8). |
| `tools/i18n_compile.py` | Checks placeholders and markup, and compiles `.mo` files. `--strict` fails while any entry is unreviewed. |
| User profile store | Holds `language`, `region`, `display_currency`, `date_format`, `time_zone` and `week_start`. |
| Config file | Holds the `i18n:` block (section 7.3). |

### 9.2 Implementation requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| T-01 | Translations are loaded once per language and cached (`st.cache_resource`), not per rerun. | Must |
| T-02 | Chart helpers set Plotly `separators` and date tick formats from the active region (F-08). | Must |
| T-03 | Tables are formatted with localized strings or a Styler before display, because `st.dataframe` number formats do not follow locale. Sorting must still work on the underlying numeric values. | Must |
| T-04 | Money and quantity inputs use a text input with `parse_num()` where comma decimals are needed, because `st.number_input` only accepts a dot decimal. | Must |
| T-05 | Built-in Streamlit widget text (file uploader "Browse files", some date picker labels) cannot be fully translated. These are accepted as known limitations for v1 and do not block release. They are wrapped or hidden where practical. | Should |
| T-06 | A CI check (`tools/i18n_compile.py`) fails the build if a `.po` file has placeholder or markup mismatches; with `--strict` it also fails while entries are unreviewed. | Must |
| T-07 | Babel's CLDR version is pinned, so formats don't change silently between releases. | Should |

## 10. Translation workflow and quality

English is written first. The other five languages live as plain `.po` files in the repo, with no paid platform. Claude drafts the translations and Sven reviews them. The extract → translate → review → compile loop runs before every release.

1. **Extract.** `pybabel extract` updates `messages.pot` from the code.
2. **Update.** `pybabel update` merges new strings into each `.po` file and marks changed ones as fuzzy.
3. **Translate.** Claude drafts the new and fuzzy strings, using `glossary.csv`, the informal form of address (G-04) and the translator comments.
4. **Review.** Sven reviews every language in Poedit (free) or a text editor, and clears the fuzzy flag on each approved string.
5. **Compile.** `python tools/i18n_compile.py` checks and compiles (T-06). Release CI uses `--strict`, so it fails if a fuzzy string remains. Don't use `pybabel compile`: it reports false errors on texts containing `%`.
6. **Visual check.** Each screen gets a screenshot pass in the longest language (de) and one comma-decimal locale.

| ID | Requirement | Priority |
| --- | --- | --- |
| W-01 | Every new or changed UI string ships in all enabled languages in the same release. Languages have no beta status. | Must |
| W-02 | Translator comments give context for short or ambiguous strings, such as "Position" as a holding versus a place. | Should |
| W-03 | Translations are kept as `.po` files in the repo and edited with free tools (Poedit or a text editor). No paid translation platform is used in v1. English has its own file too (`locales/en`), pre-filled with the source text, so Sven can correct English wording without a code change. Larger rewrites are also made in the code so the source stays clean. | Must |
| W-04 | Draft translations are marked fuzzy until Sven approves them, so an unreviewed string can never ship (T-06). | Must |
| W-05 | Legal texts (L-11) are reviewed with extra care. Before public launch, the French and Dutch privacy policy and terms should get a check by a fluent native speaker, even if unpaid, such as a friend or a user. | Should |

## 11. Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| N-01 | Performance: switching language or region re-renders the current page in about the same time as a normal rerun. | < 300 ms added over a normal rerun |
| N-02 | Formatting overhead on a 500-row holdings table. | < 50 ms |
| N-03 | Accuracy: formatting never changes the stored value. Rounding is display-only. | 0 value changes in round-trip tests |
| N-04 | Accessibility: the page `lang` attribute is correct so screen readers pronounce text properly. Colour is never the only carrier of signal meaning. | WCAG 2.1 AA |
| N-05 | Extensibility: adding a seventh language needs only a `.po` file, a glossary column and a config entry. | No code changes |
| N-06 | Privacy: locale settings count as user preferences under GDPR. They are included in data export and deleted with the account. | In line with the user management spec |

## 12. Acceptance criteria and testing

The feature is done when all Must requirements pass and the checks below are green for all six languages.

- [ ] CI shows 0 untranslated strings and 0 placeholder mismatches in every enabled `.po` file.
- [ ] A pseudo-locale build (for example `[Ġéén Çöñŧîñüé ~~~]`, about 35% longer) shows no hard-coded English and no clipped text on the five core screens: Dashboard, Screener, Portfolio, Risk and Stock Detail.
- [ ] Snapshot tests for `fmt_*` functions cover every enabled region, including de-CH apostrophes, fr narrow no-break spaces, negative values, zero, very large and very small values.
- [ ] Round-trip tests confirm `parse_num(fmt_num(x)) == x` for every comma-decimal and dot-decimal region.
- [ ] Switching language on each core screen keeps the current screen, filters and selection.
- [ ] A setting chosen on one device appears after sign-in on another.
- [ ] Before sign-in, the language switcher works and the choice carries into the profile.
- [ ] Removing a language from config falls back correctly and shows the one-time notice (C-01).
- [ ] Charts show localized separators and dates in axes and tooltips.
- [ ] Sven has approved every string in nl, fr, de, it and es (no fuzzy entries left), including the glossary, disclaimers and legal texts.

## 13. Out of scope and future phases

These items are deliberately left out of v1 and kept here so they aren't lost.

| Item | Why deferred | Likely phase |
| --- | --- | --- |
| Admin UI for i18n config | v1 uses the config file, as the logging spec does. | With the admin portal |
| Translating the admin portal | Admin-only tooling; stays English in v1, like the logs. | On demand |
| Translated provider content (company descriptions, news) | Needs a machine translation service, cost and quality controls. | v2 |
| Localized emails, notifications and PDF reports | No outbound communication in v1 scope yet. | When notifications ship |
| Long-form help and documentation site | v1 covers in-app help only (L-13). | When a docs site exists |
| Hosted translation platform (Weblate, Crowdin) | Avoids cost in v1. Worth revisiting if outside translators join. | On demand |
| More languages (pt, pl, sv, and others) | Architecture supports them (N-05). Waits for demand. | On demand |
| Regional wording variants (nl-BE vs nl-NL text, fr-BE vs fr-FR) | Formatting differs in v1, but wording is shared. | v2 (D-04) |
| Right-to-left languages | No target market in v1. | Not planned |
| Market-specific tax terms and reports per country | Belongs to the Tax epic. | Tax epic |

## 14. Decisions

All open questions were decided on 27 September 2026. There are no open items left in this spec.

| Topic | Decision | Affects |
| --- | --- | --- |
| Signal badges | Stay in English (BUY / MONITOR / AVOID / VETO / Strong Buy) in every language as a brand element. Tooltips and explanations are translated. | L-03, 8.1, G-02 |
| Form of address | Informal in every language: je / du / tu / tu / tú. | G-04 |
| Italian and Spanish | Launch with full status, the same as nl, fr and de, after Sven's review. There is no beta status. | W-01, 10, 12 |
| Swiss regions | Display currency defaults to CHF for de-CH, it-CH and fr-CH, and to EUR everywhere else. | 7.1, 7.3 |
| English default region | en-GB. | 2, 6 |
| Translation management | Plain .po files in the repo, no paid platform. Claude drafts, Sven reviews. | 10, W-03 |
| Streamlit widget texts that can't be translated | Accepted as a known limitation for v1. They don't block release. | T-05 |
| Admin portal | Stays English in v1. | 13 |

**Why informal everywhere.** It matches Uvalu's modern fintech brand (Signal Teal / Mint Pulse, signal badges) and the apps solo investors compare it with, such as Trade Republic, Revolut, N26 and Bolero. One register across all languages keeps the voice consistent. French is the one language where informal is less settled in finance. To keep "tu" from feeling overfamiliar, UI copy uses neutral labels where possible ("Add position" rather than "Add your position") and keeps a calm, precise tone.

**Why plain `.po` files.** They cost nothing, keep everything in Git, and work with the free Poedit editor. A hosted platform mainly pays off with several outside translators, which v1 doesn't have. The switch to Weblate later is easy because Weblate reads the same files.

## 15. Repo notes

How this spec maps onto the current code (branch `feature/i18n-locales`):

- UI code lives in `app.py`, `uvalu/` (shell, drawer, dialogs, components, ui, authgate) and `uvalu/pages_/`. Engine modules (`screener.py`, `risk.py`, `cash.py`, `auth.py`) also produce user-facing texts such as signal explanations, rebalancing advice and error messages.
- `locales/` holds 955 drafted entries. Each has a context note and a `file:line` source reference. The code does not yet call `_()`; the msgids are proposals for the strings the code will pass once wrapped. See `locales/README.md` for merged sentences, plurals, message contexts (`button`, `style`, `date_format`) and values translated at display time.
- 32 entries are marked "Planned (spec, not in code yet)": the Language & region settings, legal links, the first-run tour and a few formatting messages.
- Excluded from translation: `uvalu/pages_/admin.py`, admin-only messages in `auth.py`, `uvalu/logkit/`, CSS/JS, and technical errors from `fx.py`, `marketdata.py` and `prices.py`.
