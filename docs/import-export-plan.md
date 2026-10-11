# Import & export rework — decisions and plan

Decided 11 October 2026. Implemented on `feature/import-export` (11 October 2026); translations reviewed and approved.

## Goal

The Settings › Import & export card serves every user, not just the founder:

- **Export** holds only data the user entered, in one workbook.
- **Import** reads that same workbook: to restore (replace everything) or to
  bulk-add rows (rows added to an export; an empty account's export is the
  template).
- The old import of the founder's personal `beleggingen` sheet
  (`portfolio.parse_excel`) goes.

## Decisions

| # | Decision |
| --- | --- |
| IE1 | **Format: XLSX** (opens in Excel, LibreOffice, Google Sheets, Numbers). Real date and number cells, not ISO strings. A hidden `_meta` sheet carries the file-format version and app version so later imports can migrate old files. The encrypted ZIP stays the exact, admin-side restore. |
| IE2 | **Import modes: Replace + Add.** Replace = restore: wipe this account's portfolio data (positions, sold, dividends, manual cash, watchlist, custom tickers, targets, withholding) and load the file. Add = bulk import: append rows, skip exact duplicates (positions/sold: ticker + date_in + shares; dividends: ticker + ex_date; cash: date + type + amount). No row IDs in the file, so no in-place update. Both show a preview with counts and per-row errors before anything is written. |
| IE3 | **Sold dividends are recomputed on import** from the Dividends sheet: dividend records for the ticker with an ex-date between date_in and date_out, split by share count when lots overlap. Not exported. |
| IE4 | **Extra sheets:** Cash (manual entries only: deposits, withdrawals, opening balance; trade/dividend cash entries are rebuilt from the trades on import), Targets, Withholding rates, Custom tickers (watchlist tickers added by hand, with their name). |
| IE5 | **Stored-data cleanup** in one versioned migration (automatic backup first): delete `google_ticker`, `target_price`, `account` (positions/sold), `google_ticker`, `declaration_date`, `record_date`, `reinvested`, `reinvested_shares` (dividends); fill empty dividend `currency` from the exchange suffix (.SW → CHF, else EUR). The last one fixes Roche (ROG.SW) CHF dividends being counted as EUR. Code that still writes these keys (dialogs, sell_position, auto-dividend import) stops writing them. |
| IE6 | **Every imported trade posts its cash** (decided 11 October 2026, during implementation): positions post a Buy, sold rows a Buy and a Sell, in date order with automatic top-ups, after the dividend cash — like trades entered by hand. Accounts whose trades predate cash management (the founder's) get Buy/Sell and top-up entries on a Replace restore, so their balance changes; one Adjustment fixes it. |
| IE7 | **Two exports** (decided 11 October 2026): the portfolio workbook (Settings › Import & export) holds Positions, Sold, Dividends, Cash and Watchlist (ticker, name — a name marks a hand-added ticker). Settings › Privacy › Export my data holds everything: Account, Settings (one sheet, every setting as section · setting · value — withholding rates, targets, dividend frequencies and dismissals included), the portfolio sheets and Automatic cash. Import reads only the portfolio sheets; Replace deletes and restores the portfolio data and watchlist — settings stay; Add merges the watchlist. Supersedes the watchlist/custom-tickers/targets/withholding sheets of IE4. |

## Export columns

Headers are fixed English keys so a file exported in
one language imports in another; sheet names are translated (D6), so import
recognises a sheet by its headers, never by its name.

| Sheet | Columns |
| --- | --- |
| Positions | name, ticker, shares, purchase_value, fee, date_in |
| Sold | name, ticker, shares, purchase_value, sale_value, fee, sector, date_in, date_out |
| Dividends | name, ticker, shares, amount, currency, tax_rate, div_type, ex_date, date |
| Cash | date, type, amount, currency, fx_rate, note |
| Watchlist | ticker, name (name only for hand-added tickers) |

Only in "Export my data" (not imported):

| Sheet | Columns |
| --- | --- |
| Account | field, value (never a secret) |
| Settings | section, setting, value |
| Automatic cash | date, type, amount, currency, fx_rate, amount_eur, linked_to, note |

`amount` (the gross total) is exported rather than amount_per_share because it
is the stored value — a restore is exact; import also accepts an
`amount_per_share` column (amount = per share × shares). Cash rows carry
`fx_rate` for a foreign currency so a restore needs no network; empty, the ECB
rate of the day is fetched. Values the import reads literally stay English
(div_type Cash/Stock/Special, cash type Deposit/…, target kind, exchange key).

Dropped as derived or internal: purchase_price, dividends (positions + sold),
annual_return_pct, amount_per_share, tax_amount, source, trade_id, div_id,
fx_source/fx_date, cash ids/links.

## Implementation

- `workbook.py` — export, parse/validate, plan, apply.
- `cash.import_entries()` — one ledger write for typed cash + trade postings;
  `cash.manual_entries()` — the typed entries the export carries.
- `uvalu/migrations/m0002_drop_unused_fields.py` — IE5 (irreversible; the
  runner snapshots first). Also `portfolio.dividends_in_eur()` now falls back to
  the exchange currency for a dividend without one.
- Settings › Import & export, laid out as Uvalu.dc.html (Import portfolio /
  Excel export rows): upload → what the file holds + row problems → Add /
  Replace → confirm (Replace in the red danger box).
- **No separate blank template** (decided 11 October 2026): the export is the
  template. It is always offered — an empty account downloads headers only —
  and rows added to a full export import in Add mode without duplicating the
  existing ones (edits to existing rows need Replace).
- Removed: `portfolio.parse_excel` (the founder's `beleggingen` sheet) and
  `backup.export_excel`.

## Also found

- The encrypted ZIP backup (`backup._PORTFOLIO_FILENAMES`) left out
  `targets.json` and `manual_tickers.json` — fixed.
- Auto-dividend dismissals and frequency overrides (`dividend_meta.json`) are
  not in the workbook: decisions, not entered data. A Replace import resets
  them; a dismissed auto-dividend may come back.

## Later (backlog)

- Broker statement import (DEGIRO, Bolero, Saxo, Keytrade) — the onboarding
  path for new users.
- Tax-year dividend summary export (gross, foreign withholding, Belgian
  withholding per year).
- Offer the export before account deletion (with L8).
