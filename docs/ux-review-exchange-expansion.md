# UX review: exchange expansion plan

16 Oct 2026. Written in the role of expert profile [08](experts/08-ux-researcher.md), a UX researcher for an investing product, on the UI changes in the [exchange expansion plan](exchange-expansion-plan.md) (§2 and the UI list in §7). As in the [13 Oct review](ux-research-plan.md), **a persona can't replace testing with real users.** The last section adds tasks for the UX5 study.

**Evidence:** the running app (master `a4ee4ad`, founder's beta account), Screener at 1440 and 1024 px, Settings → Dividend withholding. Plus the code paths named in each finding.

## Summary

| # | Finding | Severity |
|---|---|---|
| X1 | Zurich prices are shown in euro today | High (wrong data) |
| X2 | Sorting the Price column mixes currencies | High |
| X3 | Picking an index shows fewer members than the index has | High |
| X4 | 21 cities in a single-choice list don't match how investors think | Medium |
| X5 | "Hide positions I own" misses a holding on another exchange's line | Medium |
| X6 | Share classes look like duplicates | Medium |
| X7 | New markets are empty for hours after release | Medium |
| X8 | Currency codes don't fit the Price column at 1024 px | Medium |
| X9 | Withholding per country: long list, and Belgium means something else | Medium |
| X10 | The filter bar wraps to a third line at 1024 px | Low |
| X11 | Venue badges don't match the Market names | Low |
| X12 | Index tags in the drawer | Low |

## X1. Zurich prices are shown in euro today (high)

The Screener shows Alpine Select (`ALPN.SW`) at "**€8.80**" and IVF Hartmann (`VBSN.SW`) at "**€124.00**". Both prices are in CHF. The row formats every price as EUR (`uvalu/components.py:1209`). An investor who knows the stock spots this at once and stops trusting the rest of the row.

The plan already fixes this (EX-39). **Recommendation: ship EX-39 on its own, before any new exchange.** It's a bug in what users see today, and it is independent of the expansion.

## X2. Sorting by Price mixes currencies (high)

With 7 currencies in one list, "Price ↓" puts Maersk (DKK 24,270) above every euro stock, and Icelandic prices in ISK above most others. The order means nothing, but a sorted column suggests it does.

**Recommendation:** sort Price on the EUR equivalent while still showing the native price. Then "highest price" means the same thing for every row. Put the EUR equivalent in the price tooltip ("≈ EUR 3,252"). *Update 16 Oct: superseded by plan D25. The converted value is shown on a small second line under every foreign amount, which is better than a tooltip because it's visible without hovering and works on touch screens.* Fair value, P/E, yield and margin of safety are ratios or same-currency comparisons, so they are unaffected.

## X3. An index shows fewer members than it has (high)

A user who picks "Euro Stoxx 50" expects 50 rows. With the default filters they will see fewer:

- The default **Min margin of safety −20%** hides about half of the universe (U1 in the 13 Oct review: the default filters are invisible).
- Members still loading, or with no fair value, can drop out of other filters.

"I picked the Euro Stoxx 50 and got 23 stocks" reads as broken, or as a hidden judgement.

**Recommendations:**

- With an index selected, the headline says so: "23 of 50 **Euro Stoxx 50** members pass your filters".
- Selecting an index shows which filters are hiding members, with a one-click "Show all members" that resets Min score and Min margin of safety.
- This is the same fix U1 asked for (show which default filters are active). Do both together.

## X4. 21 cities in a single-choice list (medium)

Investors in Belgium and the Netherlands think in countries and regions ("Swedish stocks", "the Nordics", "Southern Europe"), not in Reykjavik, Vilnius or Riga. A single choice also means one market at a time: comparing the Nordics means picking Stockholm, Copenhagen, Helsinki, Oslo and Reykjavik one by one.

**Recommendations:**

- *Update 17 Oct: decided as official exchange name + country ("Euronext Brussels · Belgium"), plan D10.* Show each option as "**City · Country**" ("Stockholm · Sweden", "Frankfurt · Germany"), sorted by translated country name. The city stays first, so the filter still means "where it trades" (EX-7).
- Make Market a **multiple choice** (like the Signal pills already are), with "All markets" when nothing is picked.
- Regions as one-click groups are optional; the multiple choice is the part that matters.

## X5. "Hide positions I own" misses a holding on another line (medium)

The filter compares tickers (`uvalu/pages_/screener.py:346`). Once the Screener shows one line per company (EX-4), a user who bought Airbus through a broker on Frankfurt (`AIR.DE`) still sees Airbus (`AIR.PA`) in the list with "Hide positions I own" on. The same applies to the watchlist star: starring `AIR.PA` doesn't mark the `AIR.DE` holding.

**Recommendation:** match holdings to Screener rows by company (the EX-5 identity), not by ticker, for "Hide positions I own" and for any "you hold this" hint. Add it to EX-4's requirements and tests.

## X6. Share classes look like duplicates (medium)

`INVE-A.ST` and `INVE-B.ST` both show the name "Investor AB (publ)"; Maersk A and B both "A.P. Møller - Mærsk A/S". Users will think it's the duplicate-company bug from U1 again, and won't know which line their broker sells.

**Recommendations:**

- Add the class to the name, from the ticker: "Investor AB · **B shares**".
- Search finds the forms investors type: "NOVO B", "novo-b", "NOVO.B" all find `NOVO-B.CO` (spec F-14 already ignores punctuation; add these cases to its tests).

## X7. New markets are empty for hours (medium)

The first fetch of the new exchanges takes about 3 hours (plan §6). Until then, choosing "Stockholm" can return a handful of rows or none. In today's app the cold start already shows skeletons and "Rebuilding the peer reference…" for about 40 seconds, and the 13 Oct review found that this reads as broken (U4).

**Recommendations:**

- In the Market list, mark a market still being added: "Stockholm · Sweden (adding, 312 of 746)".
- If the filter returns no rows for such a market, say why instead of "No stocks match".
- Release on a warmed server: run the first fetch before switching the release on (as UX5 already asks for the study).

## X8. Currency codes in the Price column at 1024 px (medium)

At 1024 px the Price column is about 60 px wide and fits "€19.48"; the Margin of safety header is already cut off ("MARGIN OF S…"). "DKK 24,270.00" needs roughly 60% more.

**Recommendations:**

- Write the code smaller and muted, before the number, so the number keeps its weight.
- For prices of 1,000 or more, drop the decimals ("DKK 24,270"). This needs a one-line exception in the brand guidelines' "prices 2 decimals" rule (v1.4, together with D14).
- When one market is filtered, the column header can carry the code ("Price · DKK") and the rows show numbers only. This is optional.
- Check the Watchlist and Portfolio rows, which use the same row component.

## X9. Withholding per country (medium)

Today's Settings card has six fields labelled by exchange ("Euronext Brussels", "Deutsche Börse"). The founder's values are 0, 15, 25, 26.4, 26 and 35%. Per country (D13) is right, but:

- **Length:** about 25 countries is a long form, and most users hold stocks from 3–5 countries.
- **Belgium means something else.** For a Belgian resident, the Belgian 30% is already applied as a separate layer (`portfolio.BE_WITHHOLDING_RATE`). A user who types 30% next to "Belgium" would be taxed twice in the app's figures. Today "Euronext Brussels 0" works only because the founder knows this.
- **The rule isn't obvious.** "Country where the company is registered" surprises users who bought Airbus in Paris.

**Recommendations:**

- List the countries of the user's holdings first, with their rates; the other countries come after, in a collapsed "Other countries" section.
- Show Belgium with an explanation instead of a field: "Belgian withholding (30%) is applied automatically for Belgian residents."
- Help text with an example: "The rate is set by the country where the company is registered, which isn't always where it trades. Airbus is Dutch, so its dividends follow the Netherlands rate."
- Migration: show the moved values once ("Your rates were moved from exchanges to countries. Check them.") rather than moving them silently.

## X10. The filter bar wraps to a third line at 1024 px (low)

At 1024 px the filter bar already has two lines (Search + Signal; Sector, Market, both sliders, Hide positions). An Index dropdown pushes the sliders onto a third line, and the first result row moves further down. That's acceptable, because the sliders already wrap as a group. Check it at 1024 × 800 when EX-W10 is built. A smaller "Filters" panel for narrow screens belongs to the phone-layout backlog item, not here.

## X11. Venue badges don't match the Market names (low)

The badge next to the ticker reads "XET" and "SWX", while the Market filter says "Frankfurt" and "Swiss" (soon "Zurich"). With 21 venues, users can't connect "CPH" or "ICE" to a market. **Recommendation:** the badge's tooltip gives the city and country ("Copenhagen · Denmark"). Keep the 3-letter codes; they're compact and already in use.

## X12. Index tags in the drawer (low)

These help, especially for unfamiliar names on new markets ("member of OMX Stockholm 30" says "large and liquid" to an investor). Keep them, but show at most two, and put the rest behind "+1". Order: the national index first, then Euro Stoxx 50 / Stoxx Europe 50.

## On D14 (currency codes, no symbols)

It's the right call for a list that mixes seven currencies: "kr" is ambiguous, and today's output already mixes symbols and codes. Expect a small cost in reading speed for euro-only users, who are used to "€". It's worth checking in the user study (below) rather than debating now.

## Additions to the UX5 user study

Add to the session guide in [ux-research-plan.md](ux-research-plan.md):

1. "Find an undervalued Swedish stock with a dividend." This tests the Market labels (X4), share classes (X6) and the SEK price.
2. "Show me the Euro Stoxx 50 members the model rates highest." This tests the Index filter and the member count (X3).
3. "What does this stock cost in euro?" on a DKK row. This tests the code notation (D14) and the tooltip (X2).
4. Hypothesis for the findings report: codes ("EUR 55.86") are read as fast as symbols once the user has seen a mixed-currency list.
