# Import & export rework — decisions and plan

Decided 11 October 2026. Not started.

## Goal

The Settings › Import & export card serves every user, not just the founder:

- **Export** holds only data the user entered, in one workbook.
- **Import** reads that same workbook: to restore (replace everything) or to
  bulk-add rows (a filled-in export or the blank template).
- The old import of the founder's personal `beleggingen` sheet
  (`portfolio.parse_excel`) goes.

## Decisions

| # | Decision |
| --- | --- |
| IE1 | **Format: XLSX** (opens in Excel, LibreOffice, Google Sheets, Numbers). Real date and number cells, not ISO strings. A hidden `_meta` sheet carries the file-format version and app version so later imports can migrate old files. The encrypted ZIP stays the exact, admin-side restore. |
| IE2 | **Import modes: Replace + Add.** Replace = restore: wipe this account's portfolio data (positions, sold, dividends, manual cash, watchlist, custom tickers, targets, withholding) and load the file. Add = bulk import: append rows, skip exact duplicates (positions/sold: ticker + date_in + shares; dividends: ticker + ex_date; cash: date + type + amount). No row IDs in the file, so no in-place update. Both show a preview with counts and per-row errors before anything is written. |
| IE3 | **Sold dividends are recomputed on import** from the Dividends sheet: dividend records for the ticker with an ex-date between date_in and date_out, split by share count when lots overlap. Not exported. |
| IE4 | **Extra sheets:** Cash (manual entries only: deposits, withdrawals, opening balance; trade/dividend cash entries are rebuilt from the trades on import), Targets, Withholding rates, Custom tickers (watchlist tickers added by hand, with their name). |
| IE5 | **Stored-data cleanup** in one versioned migration (automatic backup first): delete `google_ticker`, `target_price`, `account` (positions/sold), `declaration_date`, `record_date`, `reinvested`, `reinvested_shares` (dividends); fill empty dividend `currency` from the exchange suffix (.SW → CHF, else EUR). The last one fixes Roche (ROG.SW) CHF dividends being counted as EUR. Code that still writes these keys (dialogs, sell_position, auto-dividend import) stops writing them. |

## Export columns

Headers are fixed English keys (also in the template) so a file exported in
one language imports in another; sheet names are translated (D6), so import
recognises a sheet by its translated name in any of the six languages or by
its position.

| Sheet | Columns |
| --- | --- |
| Positions | name, ticker, shares, purchase_value, fee, date_in |
| Sold | name, ticker, shares, purchase_value, sale_value, fee, sector, date_in, date_out |
| Dividends | name, ticker, shares, amount_per_share, currency, tax_rate, div_type, ex_date, date |
| Cash | date, type, amount, currency, note |
| Watchlist | ticker |
| Custom tickers | ticker, name |
| Targets | as stored in `targets.json` (one row per weight) |
| Withholding | exchange, rate_pct |

Dropped as derived or internal: purchase_price, dividends (positions + sold),
annual_return_pct, amount, tax_amount, source, trade_id, div_id, fx fields,
cash ids/links.

## Also found

- The encrypted ZIP backup (`backup._PORTFOLIO_FILENAMES`) leaves out
  `targets.json` and `manual_tickers.json` — a restore loses them. Fix with
  this work.
- Auto-dividend dismissals and frequency overrides (`dividend_meta.json`) are
  not in the workbook: decisions, not entered data. A Replace import resets
  them; a dismissed auto-dividend may come back.

## Later (backlog)

- Broker statement import (DEGIRO, Bolero, Saxo, Keytrade) — the onboarding
  path for new users.
- Tax-year dividend summary export (gross, foreign withholding, Belgian
  withholding per year).
- Offer the export before account deletion (with L8).
