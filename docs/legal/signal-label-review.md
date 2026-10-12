# Signal label review

12 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)). It does not replace a formal opinion from a licensed Belgian lawyer (open item L3).

Labels reviewed: **Undervalued**, **Neutral**, **Low score**, **Fails quality screen**, **No signal** (`screener.py`, Stage 6 of [`docs/stock_valuation_algorithm.md`](../stock_valuation_algorithm.md)).

## Conclusion

The current labels are a clear improvement on BUY / MONITOR / AVOID / VETO, and the overall approach should stay. The label wording on its own is a **low** risk. Two adjacent issues carry more:

- **Medium–high: market abuse rules.** Renaming the labels does not take Uvalu out of the Market Abuse Regulation (MAR) rules on investment recommendations, and no wording could. The fair value alone already counts as an "opinion as to the present value" of a stock. So the question isn't which label avoids MAR. It's whether Uvalu meets the MAR presentation and disclosure duties. The design already covers most of them.
- **Medium: MiFID II investment advice.** On the Dashboard, the Signal column sits next to the user's own positions, with weight and P&L. That is the one place where a general signal could be read as personal advice.

Below, each point is marked as settled law, interpretation, or unclear.

## 1. MAR: investment recommendations

**Settled law.** Art. 3(1)(35) MAR defines an investment recommendation as information that recommends or suggests an investment strategy, explicitly or implicitly, about a financial instrument or issuer, "including any opinion as to the present or future value or price", intended for the public or distribution channels. A model fair value with a margin of safety meets that definition, and so does the label "Undervalued". Art. 20 MAR then requires objective presentation and disclosure of conflicts of interest. Delegated Regulation 2016/958 sets out the details.

**Interpretation.** A paid service whose core output is these signals is very likely a person "whose main business is to produce investment recommendations". In this view that is the "expert" category under Art. 3(1)(34)(i) MAR, which brings in the stricter obligations of Art. 4 of the Delegated Regulation:

- the meaning of each rating
- the time horizon
- a 12-month history of changes
- the share of covered stocks in each category

The design already meets most of this:

| Requirement | Where it is |
|---|---|
| Meaning of each rating | `SIGNAL_DEFINITIONS` and the methodology page |
| Time horizon | `SIGNAL_HORIZON` (3–5 years) |
| 12-month history | `history_for(ticker)` |
| Share per category | `signal_distribution` |
| Conflicts of interest | `FOUNDER_HOLDS_NOTICE`, at any position size, which is more conservative than required |

The gap is the producer's identity. Art. 2 of the Delegated Regulation requires the producer to be identified, and that depends on L4 (KBO registration and a business address).

**Unclear.** How MAR applies to signals produced fully by an algorithm, with no analyst behind each one, is not well settled. This is item L3 in [`docs/open-items.md`](../open-items.md), and it is the question that needs a formal opinion.

**What the labels change.** The labels only affect the objective-presentation duty: a label must not overstate what the model measured. On that test:

- **Undervalued:** acceptable, because the conditions behind it are strict (score ≥ 70, margin of safety ≥ 10% enforced in code by `MIN_MOS_FLOOR`, at least two models). It must never appear without the "Model signal" qualifier. Of all the labels it reads most like a statement of fact.
- **Neutral:** the main wording concern. "Neutral" is a standard sell-side rating, as in Overweight / Neutral / Underweight. It makes the scale *more* like an analyst's rating, not less, and it doesn't match "Low score", which describes the score.
- **Low score:** good. It is descriptive, and the methodology page states that it does not mean overvalued.
- **Fails quality screen:** acceptable, because the failed rules are named in `signal_reason`. "Quality" is an evaluative word, so "Screened out" is more neutral, but this is a minor point.
- **No signal:** no issue.

## 2. MiFID II: investment advice

**Settled law.** Investment advice means a personal recommendation (Art. 4(1)(4) MiFID II). A recommendation is personal only if it is presented as suitable for that person or is based on their circumstances, and not when it is issued only to the public (Art. 9 of Delegated Regulation 2017/565). Rules PER-1 to PER-5 keep every signal the same for all users, so the signals are general information. This is the strongest protection, and it must not be weakened.

**Interpretation: the Dashboard Holdings table.** The table (`uvalu/pages_/dashboard.py`) shows the Signal next to the user's own position, weight and P&L. The signal itself is not personalised. Seen this way, though, a user reads "your holding X: Low score", which is the same pairing that PER-5 forbids in alerts, just in static form. This doesn't make Uvalu an advisor on its own. It is still the screen an inspector would look at first, and a design choice is cheaper than an argument.

## 3. Consumer law: misleading practices

Art. VI.97 of the Belgian Code of Economic Law (WER) requires labels to be accurate. The rule that "a label must describe what the model measured" is the right test, and the current labels pass it. The translated labels are themselves legal texts, and their review is still open as L6. "Ondergewaardeerd" and "Sous-évalué" carry the same factual-claim risk as "Undervalued", so the qualifier must survive translation.

## Recommended changes, in order of value

1. **Rename "Neutral" to "Mid score".** The scale then becomes Undervalued / Mid score / Low score / Screened out (or Fails quality screen). The lower two describe the score and no longer look like analyst ratings. This touches `screener.py`, the five `.po` files, the methodology page and `docs/stock_valuation_algorithm.md`.
2. **Dashboard Holdings.** Either drop the Signal column and link each position to its stock page, or keep it with the column header "Model signal (same for every user)" and the standard tooltip. The header option is recommended, confirmed by counsel together with L9.
3. **Keep "Undervalued" tied to the qualifier everywhere,** including in translations, exports and share cards. Add a test that no export prints the label without "model signal".
4. **Finish L4.** Without a registered producer identity, the MAR disclosures are incomplete.

## Facts needed before a final view

- Target markets: Belgium only, or other EU countries? This decides whether other national regulators matter.
- Will signals appear in marketing, social media or emails? Each of those is a distribution channel under MAR.
- Is any part of Uvalu free and public? It affects who counts as "the public".

## When to involve a licensed lawyer

Get a formal opinion from a licensed Belgian lawyer on L3: MAR classification, expert status, and how MAR applies to algorithmic signals. After that, consider an informal pre-consultation with the FSMA through its fintech contact point. This review is a first pass; it doesn't replace that opinion.
