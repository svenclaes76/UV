# Demo review: financial regulation

18 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [01](../experts/01-financial-regulation-lawyer.md). It does not replace a written opinion by a licensed Belgian financial-regulation lawyer.

Reviewed: the demo as built on `feature/demo-mode` (`01612a6`), run locally in demo mode; [`docs/demo-mode-plan.md`](../demo-mode-plan.md) (decisions DM-D1–D21); the demo notice, Methodology answers and data-source texts; the beta conflicts-of-interest page and terms, which the demo still shows. Background: [briefing 01](../experts/briefings/01-financial-regulation-brief.md), [signal label review](signal-label-review.md).

## Conclusion

- **Invite-only demo for testers you know: low.** It shows the same outputs as the beta, on fewer stocks, with the same safeguards: compliant labels with the "Model signal" qualifier, the methodology one click away, a dated data basis, disclaimers on every screen, no actions addressed to the user. A fictional sample portfolio makes the per-user risk outputs even less personal than in the beta.
- **Demo shown to crowdfunding backers: medium, until L3 is answered.** Backers you don't know are an audience close to "the public". Signals on nine named, widely held stocks then look more like investment recommendations distributed to the public (art. 3(1)(35) MAR) than in an invite-only beta of acquaintances. The safeguards are probably enough for a tool that applies the same published rules to every stock, but that is the L3 question, and it becomes urgent before backers see the demo.
- **The crowdfunding campaign itself: unclear, possibly high.** If the campaign offers shares or loans in Uvalu (equity or lending crowdfunding), the campaign is an investment offer with its own rules, and the demo becomes part of its marketing (§3). If it's reward-based (pre-orders), most of this falls away. This decides more than anything else in the demo.

## 1. What changes compared with the beta

| Aspect | Beta | Demo | Effect |
|---|---|---|---|
| Audience | People the founder knows, invited, EEA, 18+, consent step | Testers you know first (DM-D1), later backers | Higher "public" character once backers see it |
| Stocks | ~3,900 listings | 9 named large caps + 1 ETF | Each signal is more visible; percentile ranks among only 9 stocks |
| User data | The user's own holdings | A fictional sample, editable per session | Less personal (lower MiFID II risk) |
| Prices | Delayed quotes with fetch time | End-of-day closes, dated | Better for objective presentation |
| Fundamentals | Provider data, ~24 h | Annual reports FY2023–2025, hand-entered, dated "as of 31 Dec 2025" | Up to 10 months old; disclosed |
| Peer reference | Universe medians | Damodaran European industry multiples | A third-party input; named on the data-sources page |
| Acceptance | Terms and "no personal advice" acknowledgement at invitation | None (no account) | The acknowledgement is lost (§2c) |

## 2. Findings

**a. Signals on nine named stocks to backers (interpretation).** Art. 3(1)(35) MAR covers information "recommending or suggesting an investment strategy" intended for distribution channels or the public. An algorithmic, rules-based label on a named share is the grey zone the L3 opinion must settle. Two features of the demo help: every stock gets a signal by the same published rule, and the notice says "not investment advice". Two features weigh the other way: the set is small and hand-picked, and the demo is shown to promote Uvalu. **Recommendation:** keep the demo invite-only until the L3 opinion is in; put the demo explicitly in the L3 question (briefing 01, demo addendum).

**b. Small-universe ranks (objective presentation, art. 3 Delegated Regulation 2016/958; interpretation).** Composite scores are percentile ranks among the 9 demo stocks. The Screener already says so ("Small universe (9 stocks): composite scores are percentile ranks within that universe"). That note should also be next to the signal on the stock page and the Dashboard, because "Mid score" among 9 hand-picked large caps means something different from the same label in the full app. **Recommendation:** a one-line "Demo: ranked among 9 stocks" note in the signal provenance on the stock page.

**c. No "no personal advice" acknowledgement (interpretation).** In the beta every user confirms it at invitation (L1). The demo has no account, so nobody confirms anything; the notice says "not investment advice" and the footer carries the disclaimer. For a free demo that's probably enough, but it's weaker. **Recommendation:** keep the banner wording; add the line "Model outputs on sample data — not a recommendation to buy or sell" to the demo notice tooltip or the first screen's subtitle; don't remove the footer disclaimer in demo mode.

**d. Producer identity (art. 2 Delegated Regulation 2016/958; L4; settled that identification is required).** The footer names "Sven Claes, trading as Uvalu" with "enterprise number: registration pending", and the legal pages give the home address. Showing this to backers you don't know adds a privacy and safety reason to L4. **Recommendation:** treat L4 (KBO registration and a business or domiciliation address) as a precondition for showing the demo to backers.

**e. Founder holdings in demo mode (settled duty, implementation gap).** The founder holds none of the 9 demo stocks today (DM-D11), so no notice is needed. But the demo workspace starts with an empty founder-holdings file: if the founder later buys one of the nine, the demo would not show the notice that the beta conflicts page promises "within 2 business days". **Recommendation:** load the founder-holdings file into the demo snapshot (or check the demo universe against it in the refresh job), so the promise holds in the demo too (open item L32).

**f. Stale fundamentals (objective presentation; interpretation).** FY2025 figures shown in October 2026 are disclosed ("as of 31 Dec 2025"), which meets the dating requirement. A stock whose situation changed materially since (profit warning, large acquisition) would still be valued on old figures. **Recommendation:** keep the date visible on the stock page (done: "Fundamentals as of"); add a sentence on the Methodology page that the demo's fundamentals are annual and may be outdated.

**g. Wording checked.** The demo notice ("not investment advice"), the Methodology answers and the data-source rows contain no buy-voice, no performance claims and no actions addressed to the user. "Reset sample" and "Give feedback" are neutral. **No change needed.**

## 3. Crowdfunding: the question that decides most

- **Equity or lending crowdfunding (Regulation (EU) 2020/1503, ECSP; Belgian prospectus law for offers outside a licensed platform; settled that rules apply, scope depends on the structure).** Marketing communications for the offer must be fair, clear and not misleading, and consistent with the key investment information sheet (art. 27 ECSP). A live demo showing model signals on listed shares, used to attract investors in Uvalu, is then part of that marketing. Claims about how well Uvalu's models work would be regulated performance claims.
- **Reward-based crowdfunding (pre-orders, perks).** Consumer law applies (review 02), not financial-offer rules. The demo is ordinary product marketing.
- **Either way:** no backtests or "the model found X before it rose" stories in campaign material (consistent with the existing decision not to publish signal performance).

**Recommendation:** decide the crowdfunding type before preparing campaign material, and put the question to the lawyer with the L3 opinion (briefing 01, demo addendum, question D-3).

## 4. Recommended changes

| # | Change | Where | Before |
|---|---|---|---|
| 1 | "Demo: ranked among 9 stocks" in the stock-page signal provenance | `uvalu/components.signal_provenance_html` (demo branch) | Testers |
| 2 | Founder-holdings file in the demo snapshot, or a refresh-job check against it (L32) | `uvalu/demo/workspace.py`, `tools/demo_refresh.py` | Testers |
| 3 | Methodology sentence: demo fundamentals are annual and may be outdated | `_FAQ_DEMO` or the demo methodology page | Testers |
| 4 | Sample-data line ("model outputs on sample data — not a recommendation to buy or sell") on the first screen | Demo notice or Dashboard subtitle (demo only) | Backers |
| 5 | Demo in the L3 question; crowdfunding type and marketing rules (L33) | Briefing 01 demo addendum | Backers |
| 6 | L4 done (KBO registration, business address) | Founder | Backers |

## 5. Open items added

- **L32** Founder holdings in the demo (§2e).
- **L33** Crowdfunding type and the rules for campaign material, including the demo (§3).

L3 (MAR classification) and L4 (producer identity) gain a demo trigger: before backers see the demo.
