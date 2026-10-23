# Demo review: data licensing

18 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [03](../experts/03-data-licensing-specialist.md). Vendor terms change often and none were attached; statements about EODHD, STOXX and Damodaran describe the usual position and the terms as quoted in the repo. It does not replace a review by a data-licensing specialist or the vendors' written answers.

Reviewed: the demo data flow on `feature/demo-mode` (`01612a6`): `tools/demo_refresh.py`, the `demo-data` workflow, `uvalu/demo/` and `demo-data/reference/sector_multiples.json`; the demo data-sources draft in [`policies/demo/`](policies/demo/); [`docs/demo-mode-plan.md`](../demo-mode-plan.md) (DM-D2, D13, D16). Background: [data-licensing review](data-licensing-review.md) and its EODHD question list (L20), [briefing 03](../experts/briefings/03-data-licensing-brief.md).

## Conclusion

- **EODHD free plan shown to people you know: medium.** Same shape as the Yahoo question in the beta (L2): a plan meant for personal use, shown to other people. The audience is small and nothing is sold, which lowers the stakes, but it isn't what the plan allows on its face.
- **EODHD free plan shown to crowdfunding backers: medium–high without a written yes.** Showing vendor data to promote a commercial product is commercial use under most data terms. DM-D2 (ask EODHD in writing first) is the right gate.
- **The other sources: low.** Company reports (facts, cited), ECB rates (free reuse with attribution) and Damodaran's averages (attribution welcome, commercial use not addressed) are fine for a free demo. The EURO STOXX 50 benchmark is the one exception worth a look (§2c).

## 1. Data flow

| Data | Source | Stored | Shown |
|---|---|---|---|
| End-of-day prices, 10 tickers | EODHD free plan | `demo-data/eod/` on the `deploy/demo` branch (private GitHub repo), read by Streamlit Community Cloud | Prices, price charts, P&L; derived: returns, risk figures, fair-value margins |
| EURO STOXX 50 index | EODHD free plan (`STOXX50E.INDX`) | Same | Not as index levels; as the Dashboard's benchmark line (value of the same euros invested in the index) and in beta |
| Dividends | EODHD free plan | `demo-data/dividends/` | Dividend amounts in the sample portfolio |
| Fundamentals | Company reports, hand-entered | `demo-data/fundamentals/` (on `master`) | Selected ratios, fair values |
| Sector P/E and P/B | Damodaran, European industry averages | `demo-data/reference/` (on `master`) | Not directly; they feed the P/E and P/B fair values; named on the data-sources page |
| FX | ECB via frankfurter | `demo-data/fx.csv` | Converted amounts |

## 2. Findings

**a. EODHD free plan (contract; the answer is EODHD's to give).** The API answers every free-plan request with "Data is limited by one year as you have free subscription", and the plan is presented as personal. Showing its data in an app others use is display to third parties; storing it in a repository that a hosting provider reads is storage and transfer the plan doesn't mention. **Recommendation:** send the DM-D2 question with the L20 list now, as decided, and add two precise demo questions (briefing 03, demo addendum): may free-plan or low-tier data be shown in an invite-only, non-paying demo; and may it be stored on GitHub and hosting infrastructure for that purpose (L38). Until the answer: testers you know only; for backers without a yes, show a recorded walkthrough or screenshots of personal-mode data you're licensed to show, not the live demo.

**b. Exchange fees (unclear).** End-of-day prices are often free of exchange display fees, but not always: London, SIX and Nasdaq Nordic have their own policies, and EODHD's terms decide whether its plans pass any fees through. This is already question 2 of the L20 list; the demo adds no new exchange. **No new item.**

**c. EURO STOXX 50 (licence; interpretation).** STOXX licenses its index data; a vendor's redistribution right for index values is often narrower than for share prices. The demo uses the index for beta (computed, not shown: L20 question 7 covers this) and for the Dashboard's benchmark line, which is a series derived from the index levels and readable as one. DM-D16 chose the app's benchmark over VWCE. **Recommendation:** ask, as part of question 7, whether a derived benchmark line counts as display; if the answer is unclear or costly, the VWCE ETF (an exchange-traded price already in the demo) is a drop-in for the line and for beta (L39).

**d. Damodaran's multiples (permission; low).** His usage rules welcome attribution and want the data "widely used"; they don't address commercial use, and the averages are built from commercial vendors' data. For a free demo with attribution (done on the data-sources page and in the reference file), the risk is low. **Recommendation:** a short email asking whether a commercial product may use the published industry averages with attribution; file the answer next to the reference file (L40). If the paid app ever uses them, this has to be settled first.

**e. Company reports (copyright and database right; settled for facts).** Individual figures from annual reports are facts and not protected; the demo takes a few dozen per company, each cited, which is far from a substantial part of any database. **No change.**

**f. ECB rates (settled).** Free reuse with source attribution, which the data-sources page gives. **No change.**

**g. No Yahoo or stockanalysis.com in the demo (checked).** Demo mode replaces `yfinance` with the snapshot stand-in, the universe is a fixed list (no ticker-list scraping), and the factor download is off. A test fails if demo mode reaches the network. This keeps L2 and L29 out of the demo. **No change.**

**h. Naming EODHD in user-facing texts (contract and objective presentation; added 18 Oct 2026 after Sven's question).** EODHD is named in four places the user sees: the demo notice ("end-of-day prices from EODHD"), a Methodology answer, and the data-source rows (Prices, Dividends) on the stock page and Methodology page; plus the demo data-sources legal page.
- *Settled:* the sources of a recommendation's inputs must be identifiable (art. 3 Delegated Regulation 2016/958, REC-3). The data-sources page and the stock page's data-source panel are where that belongs; the notice and the FAQ are not needed for it.
- *Contract, unclear until EODHD answers:* data vendors usually require attribution where their data is displayed, often with set wording or placement, and many restrict use of their name in marketing or anything that suggests a partnership. EODHD's rules are question 11 of the L20 list.
- *Practical:* naming the vendor prominently in a demo meant to promote Uvalu draws attention to the free-plan question (L38) before it's answered.

**First-pass recommendation:** name EODHD only where attribution and REC-3 need it (the data-sources page and the stock page's data-source rows); in the demo notice and the Methodology answer, say "end-of-day closing prices" and link to Data sources. Final wording after EODHD's answer to question 11 and the specialist's view (briefing 03, D-5). **Not changed yet** (L41): the translations of the two texts under review would change with it.

## 3. Recommended changes

| # | Change | Where | Before |
|---|---|---|---|
| 1 | Send L20 with the demo questions (DM-D2, L38) | Email to EODHD | Testers you don't know; backers |
| 2 | Benchmark line: ask with L20 question 7; VWCE as the fallback (L39) | `uvalu/demo/universe.INDEX_SERIES`, DM-D16 | Backers |
| 3 | Damodaran permission email (L40) | Email | Paid use; nice to have for the demo |
| 4 | Data-sources draft: add "for the demo only; not a licence to reuse the data" under Permitted use | `policies/demo/data-sources.md` | Testers |

| 5 | EODHD named only in attribution places; neutral wording in the notice and Methodology answer, after question 11 (L41) | `uvalu/shell.py`, `uvalu/pages_/help.py` | Backers |

## 4. Open items added

- **L38** EODHD free plan in the demo: display and storage, in writing (part of L20; DM-D2).
- **L39** EURO STOXX 50 benchmark line in the demo (L21, L20 question 7).
- **L40** Damodaran: commercial use of the industry averages.
- **L41** Where to name EODHD in user-facing texts (§2h).
