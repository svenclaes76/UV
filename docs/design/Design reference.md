# Design reference

One reference per screen. Where a design file in the repo (`docs/design/`) overlaps with this project, the file listed here wins.

| Screen | Reference |
| --- | --- |
| Dashboard, Screener, Watchlist, Portfolio (overview, open, closed, dividends, cash), Risk, Analysis, Settings, Methodology, Legal, About, sign-in and invitation sign-up | Uvalu.dc.html |
| States: No signal (Adyen in the Screener), peer-reference rebuild, stale-price chip, founder-holds notice, Show more (mock pages by 12; app uses 25) | Uvalu.dc.html (Tweaks › Data states; No signal and Show 25 more are always visible) |
| Version: footer marker, About (This version, What's new), update notice, reload prompt, DEV/TEST marker, error reference, maintenance screen | Uvalu.dc.html (Tweaks › Version shows each state) |
| Settings › Language & region | Uvalu.dc.html (card in Settings) |
| Admin: Users, Data feeds, Backups & restore, System | Uvalu Admin.dc.html |
| Settings › Account security (password, linked account, two-factor, backup codes, trusted devices, passkeys, sessions) | Uvalu.dc.html |
| Sign-in failure and lockout states, invite acceptance, password recovery, two-factor challenge, backup-code and passkey dialogs, Admin › Security | Uvalu Auth.dc.html |

## Superseded repo files
- `docs/design/Uvalu.dc.html`: older copy of the main app. Replace it with this project's `Uvalu.dc.html`.
- `docs/design/Uvalu Cash Management.dc.html` and `Uvalu Dividend Management.dc.html`: merged into `Uvalu.dc.html` (Portfolio › Cash and Dividends, Add/Edit dialogs, Dashboard tiles). Keep them as history only.

## Decisions built into the reference
These match the deliberate deviations recorded in `docs/design/README.md` and the 2026.10.x releases. Don't count them as gaps.
- Dividends: no declaration date, record date or frequency in the dialogs or log rows; no "Withholding by domicile" card; no "Import from market data" button.
- Cash: buys are never blocked by the balance; a shortfall posts a linked top-up. Withdrawals and fees that would go below zero are blocked.
- Free beta: no checkout or billing; plan shown as "Free beta · by invitation"; no "Contact support" banner on Methodology.
- Signals: Undervalued / Neutral / Low score / Fails quality screen / No signal. Provenance is one quiet line under the page title. Price above model fair value is amber; red is kept for a failed quality screen.
- Settings order follows the code: Language & region, Account security, Display, Target allocation, Dividend withholding, Import & export, Model settings, then Privacy, Plan and Legal.
- No Data & alerts section in Settings, in the design or the code (see Code removals). Dividend withholding is its own section. Data delay is shown in the provenance line under page titles.
- Supporting pages (Settings, Methodology, Legal, About): back link, 24px title, 200px section rail, 760px content.
- All page titles 24px; all back links read "← Back to …".
- "Margin of safety", never "Upside". A negative margin is amber, not red.
- Score bands 70 and 40, matching the Undervalued and Low score thresholds.
- Holdings last column is P&L against average cost.
- Screener filters: a stock without a score passes while Min score is 0, as in the code (`screener.py`, missing score counts as 0). Quality-screen and No signal stocks therefore show at the default filters and drop out as soon as Min score is raised. A stock without a margin of safety (No signal) also passes the margin filter at its default of −20%. The code differs here: missing margin counts as −999, so No signal stocks never appear (`screener.py` line 333). Change the code to let a missing margin through while the filter is at its default.
- Colours follow Brand Guidelines v1.3 (9 Oct 2026): `--link` for link text (#167A60 light, #3FBF98 dark); `--up-txt` for positive text and the Undervalued badge; `--amber-txt` / `--amber-bg` / `--amber-fill` for caution (text #854F0B light, #E0B94D dark; fill #C98A3A); Signal Teal #1A8C6E only for fills, borders and selected states; Mint Pulse never as text on light. `--faint` is decoration only; readable text uses `--muted`. Fair-value ladder fills: `--up-txt` below, `--axis` within ±3%, `--amber-fill` above, on a `--uv-track` track. Badges use the token pairs; Fails quality screen is navy (dark: #1E2D4A with a hairline); No signal uses a grey wash with `--muted` text.
- Brand v1.3 components: provenance values in 11.5px monospace with a quiet underlined "Methodology →"; stale chip uses the Material `warning` symbol; notice order below the header: update notice, reload prompt, then the beta bar. The beta bar is a full-width `--soft` strip (6px × 28px padding, left-aligned, hairline bottom border) with "Beta" in `--up-txt`; founder notice is the 12px muted disclosure sentence; radii only 4/6/8/12px; uppercase only below 12px; 2px `:focus-visible` ring (teal light, mint dark); supporting pages left-aligned on the gutter with a 32px gap between section list and content; 12-colour categorical chart palette. Icons are Material Symbols (outlined), 16px inline and 20px in navigation, in all three mockups. Admin and Auth (dark only) use the same v1.3 tokens: `--link` for link text, `--muted` for readable secondary text, radii 4/6/8/12px.

- Authentication (Brand v1.3 and legal): password sign-in only in the beta. Google is not in the beta: no Google button on the sign-in screens while it is unavailable; shown as "Not in the beta" in Settings and Admin; provider screens are marked "later"; the beta privacy notice in `legal-docs.js` no longer describes Google sign-in (apply the same to `docs/legal/policies/beta/privacy-notice.md`). No Microsoft, no passkey sign-in; full footer disclaimer, producer and legal links on the sign-in panel; invitation acceptance with EEA country, refusal state and three separate unticked boxes stored with version and time; re-acceptance screen at sign-in when a text changes; password reset via admin while there is no email sender; MFA always required for admins; accounts by invitation only (no auto-provision); active sessions without location; uvalu.app addresses. Still to confirm in the privacy notice: the breached-password check (Have I Been Pwned, hash prefix) and the 30-day trusted-device cookie.

## Label changes for the code
The design wording wins. Change the code's source strings and update all six languages.
- "Methodology & help" → "Methodology": page title, user menu, back links and About notes (`uvalu/pages_/help.py`, `uvalu/shell.py`).
- "Account" → "Account security": Settings section list and card heading (`uvalu/pages_/settings.py`, `_SECTIONS` and the Security header).
- "Portfolio" → "Target allocation": Settings section list only, so it matches the card heading and doesn't clash with the Portfolio page (`uvalu/pages_/settings.py`, `_SECTIONS`).

## Code removals
- Settings › Data & alerts: remove the section from `uvalu/pages_/settings.py`. That covers the `set-data` entry in `_SECTIONS`, the price refresh interval row, and the ex-dividend, dividend cut/suspension and dividend increase alert rows with their weight threshold. Keep the Dividend withholding card and give it its own anchor, `set-withholding`, between Target allocation and Import & export. Before removing, check what reads these settings (`refresh`, `alert_ex_div`, `alert_dividend_size`, `alert_div_cut`, `alert_div_increase`). Dashboard flags and the price refresh timer either need fixed defaults or need to go too. Drop the matching translation strings in all six languages.

## Deferred to later implementation
Kept in the design and not built in the code yet. These are decisions for a later release, not gaps for this assessment.
- Phone and tablet layouts. The reference is desktop only (from about 920px). The code's existing phone behaviour, such as the document picker replacing the section rail, is not assessed until these layouts are designed.
- Settings › Privacy: Export my data, Delete account and Privacy contact (privacy@uvalu.app, already defined in the code). They cover the GDPR self-service rights; until they ship, the privacy notice must explain how to request them by email.
- Settings › Legal: no-personal-advice acknowledgement. Checked against the legal requirements (DIS-2, TOU-9, E1, E2 in `docs/legal/compliance-implementation-plan.md`; privacy notice § records). The design matches: a separate unticked box at invitation acceptance, and in Settings › Legal the accepted text version, date and time with a link to Terms §4. To build it, the code needs:
  - a consent record per user (document, text version, language, time), stored for the life of the account plus 10 years, as the privacy notice states. `consent.py` is planned but not in the repo;
  - the invitation page with three separate unticked boxes (18+, Terms and Privacy with versions, no-advice) plus country of residence (EEA only);
  - re-acceptance at the next sign-in when the text changes, and for existing users and testers who never accepted;
  - the Settings › Legal row reading from that record.
  The Settings row only shows the record; the legal requirement is the box at sign-up. Build both together.
- Settings › Plan card: "Free beta · by invitation" now; it becomes relevant when paid plans start.

## Check with real translations
Found with simulated text about 40% longer (typical for German and Italian) on Dashboard, Screener, Watchlist, Portfolio and Risk. Settings and Analysis were not checked. Recheck these once real translations are in.
1. Top navigation: the price status ("Delayed · 17:35") is cut off at the right edge.
2. Buttons wrap onto two lines: Add position, Add ticker, Export CSV, Reset filters, Refresh.
3. Watchlist column headings run off the table (Yield is cut off).
4. Dashboard and Portfolio summary tiles: two-line labels put the numbers in a row out of line.
5. Holdings legend breaks into narrow multi-line columns beside the card title.
6. Holdings and Screener column headings take two lines; readable, but the header row grows.
7. Screener slider labels (e.g. Min margin of safety −20%) push the value into the label.
