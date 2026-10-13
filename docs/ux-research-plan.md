# UX review and research plan

13 Oct 2026 · First pass in the role of expert profile [08](experts/08-ux-researcher.md): a UX researcher for an investing product. There is no separate persona file for this role. **A persona can't replace testing with real users**, and the profile itself warns against that. So this document has two parts:

1. An expert walkthrough of the running app (master `b1014f9`, the founder's beta account and portfolio, 13 Oct 2026). It covers the Dashboard, Screener, Risk and the stock drawer, from the point of view of a self-directed retail investor seeing them for the first time.
2. A ready-to-run research plan: hypotheses, a recruitment screener and a session guide for 6–8 real participants.

## Part 1: Expert walkthrough

| # | Finding | Severity |
|---|---|---|
| U1 | The Screener's first screen contradicts its own headline | High |
| U2 | Signals appear next to the user's own position | High (legal) |
| U3 | Three portfolio totals and three returns on one Dashboard | Medium |
| U4 | Cold start: minutes of "No signal" and loading skeletons | Medium |
| U5 | Risk page jargon and labels that contradict their numbers | Medium |
| U6 | Negative margins of safety shown as "−125%" | Medium |
| U7 | Smaller inconsistencies | Low |

### U1. The Screener's first screen (high)

The headline reads "2033 of 3942 **European** stocks pass your filters". The top 25 Undervalued results include:

- **Non-European companies:** CF Industries, Kinross Gold, EOG Resources, Hartford, APA and AngloGold Ashanti.
- **The same company twice:** EOG as `1EOG.MI` and `EO5.DE`; Hartford as `HFF.DE` and `1HIG.MI`.
- **The #1 result, Investor AB, is a currency error** with an 86% margin of safety (valuation review V1).

An investor who knows these names will distrust everything else in the first minute. "Pass your filters" also appears when the user hasn't set any: the default "Min margin of safety −20%" silently hides about half the universe.

**This depends on V1 and V2.** Until those are fixed, a usability test would spend its sessions on this one screen. Also show which default filters are active.

### U2. Signals next to the user's own position (high, legal)

- **The stock drawer**, opened from the Risk page, shows "Model signal: Screened out" in the same panel as *Shares held 24, Position value €1,926, Unrealised P&L −€22*.
- **The Risk page's "Flag" column** on the user's holdings mixes "Screened out" (a model signal) with "High risk" (a position risk rating). A column called *Flag* next to *your* positions reads as "act on these".

This is the pairing the signal label review flagged for the Dashboard (L13) and that PER-5 forbids in alerts. The Dashboard got its "Model signal" header, but these two places didn't.

**Hand it to the financial-regulation lawyer (#1)** together with L9 and L13. A design option: keep the signal in the drawer's header, and move the position block to a separate tab or section headed "Your position". Rename the Risk "Flag" column, or remove the signal from it.

### U3. Three totals and three returns on the Dashboard (medium)

| Where | Figure |
|---|---|
| "Current value" | €26,550, −23.5% unrealised (incl. €1,088 cash) |
| Sector allocation total | €25.5K (invested only) |
| "Portfolio value over time" | €23,662, +7.5% "past year · incl. deposits" |
| "Total return" | −€4,937, −14.8% incl. dividends |

Each figure is probably correct on its own definition, but nothing reconciles them. A participant will ask "so how much do I have, and am I up or down?". One value, one return as the headline, and the others labelled as views of it (invested only, last 12 months, including deposits).

### U4. Cold start (medium)

After a restart the app shows "Rebuilding the peer reference… Signals show 'No signal'" for several minutes. The Screener goes from "0/2665 companies scored" to 3,942. For a first visit, or for a test session, that reads as broken.

- For testing, warm the staging server before each session.
- For the product, the daily build (Q1) removes the restart dependency.

### U5. Risk page wording (medium)

- **Factor names:** "Mkt-RF, SMB, HML, RMW, CMA, WML" and "Sector HHI" mean nothing to most retail investors. The plain-language names next to them help, so lead with those and move the codes to a tooltip.
- **"Low · +0,75"** for the small-cap tilt: a loading of 0.75 is a clear tilt, but the label says *Low* because the threshold is 1.5. Users will read "Low" as "not exposed".
- **"Real Estate at 30% is above the model's 30% reference level":** 30.2% rounded to 30% next to "above 30%" looks like a bug. Show one decimal when near the threshold.
- **"Sharpe ratio … below 1.0 in two consecutive risk reports (was −0,32 at 13/10/2026)":** both reports were on the same day.
- **Decimal separators:** the Dutch locale shows "0,71" and "−0,21" but the explanatory text says "above 1.5" and "below 1.0".

### U6. Negative margins of safety (medium)

The drawer shows "Margin of safety **−125,3%**", with per-model values down to −216.7%, and the fair value in **green**. A margin below −100% has no intuitive meaning. Retail users read a red-ish "−125%" as a loss, and green as "good".

- Above the fair value, say "Price is 2.3× the model fair value" or "125% above".
- Keep the fair value's colour neutral.
- Cap the per-model percentages at a readable range.

### U7. Smaller points (low)

- The drawer says "basis · 2 of 6 models" but lists three model values (EPV and two dividend models). If the two dividend models count as one, say so.
- The Dashboard chart offers the S&P 500 next to the Euro Stoxx 50 as a benchmark. That's fine, but think about which one is the default for a European product.
- "Top movers today" appears while the header says the market is **Closed**, and prices are delayed. Consider "Last session's movers".

## Part 2: Research plan

### When to run it

**After V1, V2 and Q1** (currency, universe, signal stability), on a warmed staging server with a realistic demo portfolio. Running it earlier spends paid sessions on known defects.

### What we want to learn

Hypotheses, each with what would refute it:

| # | Hypothesis | Refuted if |
|---|---|---|
| H1 | Users understand "model fair value" as an estimate, not a price target | ≥ 3 of 8 describe it as "what the stock will go to" |
| H2 | Users understand margin of safety, including negative values | ≥ 3 of 8 can't explain a negative margin |
| H3 | "Undervalued / Mid score / Low score / Screened out" are read as **descriptions**, not instructions | ≥ 2 of 8 say they would buy or sell *because of* the label (key input for lawyer #1) |
| H4 | Users notice and understand why a stock is Screened out | ≥ 3 of 8 can't say why |
| H5 | The risk score and bands are understood as a description of the portfolio | ≥ 3 of 8 read Moderate or High as "you should change something" |
| H6 | Users find the Methodology page when they doubt a number | ≤ 4 of 8 find it unprompted |
| H7 | The Dashboard tells users how much they have and whether they are up | ≥ 3 of 8 give the wrong value or direction |
| H8 | Users would pay €5–15 a month, and for what | Qualitative: which features they name, and at what price they hesitate |

### Participants

- **6–8 people per round,** self-directed retail investors living in Belgium or the Netherlands, who manage their own stocks (not only funds).
- **Mix:**
  - experience: 3 with under 3 years, 3 with 3–10 years, 2 with over 10
  - portfolio size: under €25k, €25–100k, over €100k
  - at least 2 who describe themselves as value or dividend investors
  - at least 2 who mainly invest in funds or ETFs and pick a few stocks
- **Exclude:** finance professionals (advisers, analysts, bank employees), people who know the founder, and anyone in a previous round.
- **Incentive:** a €50–75 voucher per 60-minute session.
- **Sessions:** in Dutch or English, remote, moderated.

### Recruitment screener

1. Where do you live? *(Belgium / the Netherlands / other EU → continue; outside the EU → stop)*
2. Do you work, or have you worked in the last 5 years, in financial services, as an adviser, analyst, broker or bank employee? *(yes → stop)*
3. Do you hold individual stocks that you chose yourself, through a broker or a bank? *(no → stop)*
4. How long have you been picking individual stocks yourself? *(under 1 year / 1–3 / 3–10 / over 10)*
5. Roughly what is the value of your investments in stocks and funds? *(under €10k / €10–25k / €25–100k / over €100k / prefer not to say)*
6. Which best describes how you choose stocks? *(value or cheap relative to earnings / dividends / growth / tips and news / funds mainly / other)*
7. Which tools do you use now? *(broker app / spreadsheet / Morningstar / Simply Wall St / TradingView / other)*
8. Have you paid for an investing tool or newsletter in the last 2 years? *(yes, which / no)*
9. Can you do a 60-minute video call with screen sharing, in Dutch or English?

### Session guide (60 minutes)

**0–5 min · Introduction and consent.**

- Explain that we are testing the product, not the participant, and that there are no wrong answers.
- Ask them to think aloud.
- Get recording consent: what is recorded, who sees it, deletion after 6 months (GDPR). Give them the information in writing beforehand.
- Say clearly that **nothing in the session is investment advice** and they shouldn't act on any figure they see.

**5–10 min · Background.** How do you decide to buy or sell a stock? What do you look at? What tool would you like to throw away?

**10–40 min · Tasks.** Use a demo portfolio, not their own data. Don't explain the interface during tasks.

| Task | Prompt | Observe |
|---|---|---|
| T1 | "Have a look around the start page. Tell me what you see." | First impressions; U3: how much do I have, up or down? |
| T2 | "Find European companies that this tool thinks are cheap right now." | Screener use, filters, trust in the list (U1); do they open Methodology? |
| T3 | "Pick one of them and tell me what the tool says about it." | Fair value, margin of safety, signal reading (H1–H3) |
| T4 | "This stock is marked Screened out. What does that mean?" | H4 |
| T5 | "This is your portfolio's risk page. How risky is this portfolio, in your words?" | H5, U5, VaR comprehension |
| T6 | "You doubt one of the numbers. Where would you check how it's calculated?" | H6 |

**40–50 min · Comprehension probes.** Neutral wording, one at a time:

- "What does *model fair value* mean to you?"
- "What does a margin of safety of −40% mean?"
- "If a stock you own showed 'Low score', what would you think? What would you do?" *(record the exact words; this is the advice-perception question for lawyer #1)*
- "What does 'Moderate risk' say about this portfolio?"
- "What does 'VaR 95% (1D) −1.5%' mean?"

**50–57 min · Value and price.**

- Which part would you miss if it disappeared?
- At what monthly price would it be too expensive to consider? Too cheap to trust? A bargain? *(Van Westendorp, light)*

**57–60 min · Wrap-up.** Anything we didn't ask? Thank them, and confirm the voucher.

### Scoring and reporting

- **Per task:** success, partial or fail, with a note.
- **Per comprehension probe:** correct, partial or wrong, coded against the definitions on the Methodology page.
- **Findings:** each rated critical, serious or minor, with a quote or clip and a recommendation.
- **Advice-perception answers** (H3, H5) are quoted in full in a separate section **for the financial-regulation lawyer**.
- **Data handling:** recordings in an EU-hosted store, deleted after 6 months. Participant names stay out of the report.

## Recommended changes, in order of value

1. **Fix V1, V2 and Q1 before any user test.** U1 comes from them (UX5).
2. **Signal next to own position:** the drawer layout and the Risk "Flag" column, reviewed with lawyer #1 (UX1).
3. **Dashboard:** one headline value and return, with the others labelled as views (UX2).
4. **Negative margin of safety wording,** and a neutral colour for the fair value (UX3).
5. **Risk page wording:** plain names first, factor labels that match the numbers, threshold rounding, same-day "consecutive" reports, decimal separators (UX4).
6. **Run the study:** 6–8 participants, with the screener and guide above (UX5).
