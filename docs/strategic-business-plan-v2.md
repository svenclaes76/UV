# Strategic Business Plan v2: Uvalu.app
*A solo, bootstrapped, low-risk experiment — built for myself, in my free time, with an AI pair-programmer.*

---

## Why This Replaces v1

[strategic-business-plan.md](strategic-business-plan.md) (v1, Sept 2026) modeled Uvalu as a 2-founder, VC-style
SaaS: €500K seed, a Series A, 10 hires by 2029, 200K users. That's not this project. This version starts from
the actual constraints:

- **Solo** — one person (you) + an AI coding partner (me). No co-founder, no employees, ever, unless the
  business earns its way there.
- **Free time only** — this is not a full-time bet. No quitting a day job, no runway pressure.
- **Minimum investment** — bootstrapped from pocket change (hosting + a domain), not funding rounds.
- **Low risk** — no debt, no investors to answer to, nothing that can't be paused or unwound in a weekend.
- **Personal use first** — you are user #1. Commercial success is an experiment layered on top of a tool
  you'd want regardless, not the reason the tool exists.
- **Fun is a real success metric**, not a slogan. If it stops being fun, that's a legitimate reason to slow
  down or stop — there's no sunk cost forcing continuation.

Every number in this document is a working assumption, not a commitment — adjust freely as reality tells you
more (especially the hours/week figure in [Section 3](#3-the-operating-model), which only you know).

---

## Table of Contents
1. [What We Actually Built (Last ~40 Days)](#1-what-we-actually-built-last-40-days)
2. [Executive Summary](#2-executive-summary)
3. [The Operating Model](#3-the-operating-model)
4. [Product Scope](#4-product-scope)
5. [Who It's For](#5-who-its-for)
6. [Go-to-Market — Deliberately Small](#6-go-to-market--deliberately-small)
7. [Monetization — Optional, Not Required](#7-monetization--optional-not-required)
8. [Financial Plan](#8-financial-plan)
9. [Risk Management](#9-risk-management)
10. [Milestones (Not a Roadmap)](#10-milestones-not-a-roadmap)
11. [What Success Looks Like](#11-what-success-looks-like)

---

## 1. What We Actually Built (Last ~40 Days)

This is the evidence the model works, pulled straight from the repo's own history — not aspiration.

**Timeline**: first commit `v0.1` on 2026-07-05; working MVP tagged `v1.0.0` on 2026-07-30. Then, in a
concentrated stretch from 2026-08-30 to 2026-09-14 (roughly two weeks of elapsed time, worked in evenings/
weekends around whatever else was going on), **nine releases shipped**: v1.1.0 → v1.9.0. Since 2026-08-06,
that's **~180 commits** and the test suite grew to **1,273 tests**, all currently passing.

What actually got built, release by release:

| Release | Date | What shipped |
|---------|------|---------------|
| **v1.1.0** | Aug 30 | Full valuation + risk engine rebuild (WS-1…WS-18): `marketdata.py`, `scoring.py`, `portfolio_enrichment.py` — sector/PEG-aware fair value, graduated DDM, analyst dispersion, trend vetoes |
| **v1.2.0** | Aug 31 | Instant-paint performance pass — every screen (Dashboard, Portfolio, Risk, Screener, Watchlist) paints immediately instead of blocking on a full recompute |
| **v1.3.0** | Sep 1 | Data-integrity pass (WP-DQ1…DQ10) — live-price margin-of-safety, real sector concentration (HHI), fair-value sanity clamps, `docs/data-contracts.md` |
| **v1.4.0** | Sep 2 | Fixed a blank fair-value ladder bug affecting a real slice of the universe |
| **v1.5.0** | Sep 6 | Structured logging subsystem (`uvalu/logkit/`) — config, redaction, retention, event taxonomy |
| **v1.5.1** | Sep 9 | Fixed a real correctness bug: the Risk page showed a green gauge under a "Moderate risk" label — unified `risk.RISK_BANDS` as the single source of truth |
| **v1.6.0** | Sep 10 | Fair-value coverage overhaul (FV-1…FV-8) — DDM/EPV no longer silently vanish for trough-earnings or thin-basis payers, plus a 10-finding self-review pass |
| **v1.7.0** | Sep 12 | Built a standalone valuation audit tool (`tools/valuation_audit.py`) and used it to catch two real spurious "Strong Buy" bugs (an untraded instrument, a per-share fundamentals outlier) before they reached a user |
| **v1.8.0** | Sep 13 | Ground-up auth overhaul (M1–M6): per-account lockout, session tracking, Google OAuth, invite-only accounts, TOTP 2FA + backup codes, admin-assisted password recovery |
| **v1.9.0** | Sep 14 | First-admin bootstrap for a genuinely fresh install, docs reorganization |

**The honest reality check**: that two-week sprint was an unusually intense burst, not a sustainable free-time
pace. A side project done around a day job realistically ships at a fraction of that speed. This plan assumes
something far more modest going forward (see [Section 3](#3-the-operating-model)) — the sprint proves the
*ceiling* when you lean in, not the baseline you should plan around.

**What this proves, concretely**: the product is real and working (v1.9.0, feature-complete for personal use —
screener, portfolio tracker, dashboard, 8-stage risk engine, multi-user auth with OAuth/2FA, encrypted backups,
admin portal), the AI-pair-programming workflow produces genuinely correct, tested, documented software at a
pace one person alone couldn't match, and the codebase is disciplined enough (data contracts, an audit tool,
1,273 tests) to keep building on without it collapsing under its own weight.

---

## 2. Executive Summary

**Uvalu.app** is a personal-first, quantitative stock screening and portfolio management tool for European
value investors, built solo with AI assistance. It exists first to serve its own creator's investing decisions;
whether it becomes a small, real side-income source for a wider circle of EU retail investors is a genuine
open experiment, run at zero financial risk.

### What changed from v1
| Dimension | v1 (rejected) | v2 (this plan) |
|---|---|---|
| Team | 2 founders + 10 hires by 2029 | 1 person + AI, indefinitely |
| Funding | €500K seed + €5M Series A | €0 external — hosting costs only |
| Infra | AWS migration, Kubernetes | Current self-hosted VPS, unchanged unless load forces it |
| Users targeted | 200,000 by 2029 | You, first. A few dozen to a few hundred, if it's fun and useful to others |
| Pace | Full-time, 2-week sprints, fixed roadmap | Free-time, no fixed cadence, roadmap driven by "do I want this for myself" |
| Risk posture | Funding runway, hiring, regulatory exposure at scale | Nothing that can't be shut down in a weekend with no one owed anything |
| Success metric | Revenue, users, market share | Personal usefulness + genuine enjoyment first; revenue and users are a scoreboard, not a requirement |

---

## 3. The Operating Model

### Team
- **You**: product direction, domain expertise (you're the target user — a European value investor), final
  call on every decision, the only person with financial or legal exposure.
- **Claude (AI pair-programmer)**: implementation, code review, docs, release management, day-to-day
  engineering — the role that let the last 40 days ship 9 releases without a second human engineer.
- No hires. If the project ever earns enough to justify one, that's a milestone to *revisit* this plan, not
  an assumption baked into it.

### Time budget
Pick a number that's honestly sustainable and revisit it monthly — this plan uses **5-10 hours/week** as an
illustrative default. At that pace, expect roughly one meaningful shipped improvement every 1-3 weeks, not the
sprint's one every 1-2 days.

### Legal structure
Given "minimum investment, low risk," the recommended default is to **not incorporate yet**. Belgium has a
lightweight status for exactly this (self-employed as a secondary occupation — *bijberoep zelfstandige*) that
covers occasional/small income without the overhead v1 assumed (Uvalu BV, Brussels HQ, €10K legal setup budget).
Incorporate only if a real trigger shows up — e.g., recurring paid revenue that's better held at arm's length
from personal liability, or a partner/investor who requires it. Until then: no company, no BV, no yearly
corporate filing burden.

*(This is a default, not a legal opinion — worth 30 minutes with a Belgian accountant once there's real
revenue, not before.)*

### Tools
Unchanged from v1 where they're already free/cheap: GitHub (code, issues), the existing self-hosted VPS.
Drop anything that assumed a team: no Linear, no Figma retainer, no Notion — a markdown file in the repo is
enough for one person.

---

## 4. Product Scope

Everything already shipped stays — it's built, tested, and useful:

| Feature | Status |
|---|---|
| Screener (6-model fair value, multi-exchange) | Live |
| Portfolio Tracker | Live |
| Dashboard | Live |
| 8-stage Risk Engine | Live |
| Stock Analysis deep-dive | Live |
| Multi-user auth (OAuth, 2FA, invite-only) | Live |
| Encrypted Backup/Restore | Live |
| Admin Portal | Live |

### What's explicitly *not* planned (dropped from v1)
- Mobile app (React Native) — a large, ongoing maintenance surface for no personal-use benefit.
- Public REST API — real security/versioning burden with no current user asking for it.
- Paid data-provider migration off yfinance — only revisit if it actually breaks (see
  [Risk Management](#9-risk-management)), not preemptively.
- AI-powered "insights" / social features — fun to imagine, but scope creep against a personal tool; revisit
  only if it'd genuinely help *your own* investing.

### What might get built, in rough order of "would I personally use this"
1. Whatever friction you hit *yourself* using it for real investing decisions — that's the only backlog that
   matters day one.
2. Small polish/quality-of-life items from your own usage.
3. A lightweight way for a handful of invited friends to use their own portfolios, if you want company.
4. Only after (3) has organic pull: a simple way for someone to pay, if they ask to.

---

## 5. Who It's For

- **Primary**: you. The tool's job is to make your own European value-investing decisions better and faster.
- **Secondary (optional, invite-only)**: a small circle — friends, ex-colleagues, people from investing
  forums you're already part of — who you'd trust with an invite link, the same invite-only model already
  shipped in v1.8.0's auth overhaul.
- **Explicitly not a target**: the general public, cold-acquired users, anyone requiring paid support,
  onboarding flows, or SLAs. If a wider audience wants in, invite-only + word of mouth is the only
  acquisition channel — no ads, no paid marketing, no partnerships to negotiate.

v1's TAM/SAM/SOM sizing (50M EU investors, 200K target users) is dropped entirely — it's not a meaningful
input at this scale and pace.

---

## 6. Go-to-Market — Deliberately Small

No paid channels, no growth targets, no funnel. If commercial success happens, it happens organically:

- **Word of mouth** from the invite-only circle in Section 5.
- **A single, low-effort public post** when/if you feel like it (e.g. a "Show HN" or a niche investing
  subreddit) — optional, one-shot, not a campaign.
- **No SEO strategy, no content calendar, no ad spend, no affiliate deals, no broker partnerships.** All of
  these require ongoing time or money this plan explicitly avoids spending.

If organic interest ever outpaces what invite-only + a VPS can comfortably handle, that's a good problem —
revisit scaling *then*, funded by whatever revenue it's already generating, not upfront investment.

---

## 7. Monetization — Optional, Not Required

The tool works fully for personal use without ever charging anyone. Monetization is an experiment to run
*if and when* organic demand shows up (someone outside your invite circle asks to pay, or an invited friend
says they'd pay to keep access) — not a plan to execute on a schedule.

### If/when it happens
- Keep it to a single simple tier (e.g. **€5-10/month** or a one-time supporter price) — no multi-tier
  pricing ladder, no annual-discount math, no affiliate revenue share. Complexity here costs your free time
  for a return that, at this scale, won't matter financially.
- Payment via an existing low-effort processor (Stripe or similar) — a few hours of integration once, not an
  ongoing operational burden.
- Any money earned is close to pure profit above the hosting cost in [Section 8](#8-financial-plan) — there's
  no CAC, no sales cost, no team to pay.

### What this deliberately skips from v1
No CAC/LTV modeling, no churn targets, no NPS goals, no funding-round math. At a few dozen to a few hundred
users, none of that machinery earns its keep — it's overhead for a business that doesn't exist yet.

---

## 8. Financial Plan

### Costs (annual, realistic)
| Item | Cost | Notes |
|---|---|---|
| Domain | ~€15/year | Already owned (uvalu.app) |
| VPS hosting | ~€10-30/month (~€150-350/year) | Current self-hosted setup, unchanged |
| Backups/storage | ~€0-5/month | Already covered by the encrypted backup feature |
| Optional: paid market-data API | €0 unless/until yfinance breaks | See [Risk Management](#9-risk-management) — not budgeted preemptively |
| Optional: payment processor fees | ~2-3% of any revenue, only if monetized | Self-funding, not a cash outlay |
| **Total realistic annual cash outlay** | **~€200-400/year** | Less than one month of v1's proposed team payroll |

No salaries (this is unpaid free-time work, by choice, unless/until revenue justifies otherwise), no seed
funding, no Series A, no marketing budget, no legal/incorporation costs until the trigger in
[Section 3](#3-the-operating-model) is hit.

### Revenue (if pursued at all)
Deliberately not projected as a target. If Section 7's optional tier gets turned on: even a handful of paying
users (say, 5-20 people at €5-10/month) covers hosting costs several times over and turns this into a small
profit — which was never the point, but is a nice outcome. There's no minimum revenue this plan needs to hit
to be considered a success (see [Section 11](#11-what-success-looks-like)).

### Break-even
Effectively **already at or near break-even** given the current ~€200-400/year cost floor and zero revenue
requirement — this isn't a "path to profitability" plan, it's a "stay cheap enough that profitability is the
default state" plan.

---

## 9. Risk Management

Risk here means "things that could make this stop being low-risk or stop being fun" — not investor-return risk.

| Risk | Why it matters here | Mitigation |
|---|---|---|
| **Burnout / unsustainable pace** | The last 40 days' 9-release sprint is not repeatable indefinitely on top of a day job — this is the single biggest real risk to the project's survival | Pick a genuinely sustainable hours/week ([Section 3](#3-the-operating-model)) and treat missing a week as fine, not a failure |
| **Losing the fun** | If it becomes an obligation, the entire premise (do this because you want to) collapses | Explicit permission to pause, slow down, or stop with zero sunk-cost guilt — no investors or users are owed continuity |
| **yfinance dependency** | Free data source could change or break | Already partially mitigated (local caching, `docs/data-contracts.md`); a paid fallback (Alpha Vantage, Twelve Data) is a same-day fix if it ever comes to that, not a standing cost |
| **Scope creep** | Easy to keep adding features "because AI makes it fast" until it's a second job | Section 4's explicit "not planned" list; re-check any new feature against "would I personally use this" |
| **Regulatory (investment-advice classification)** | Real for a paid, publicly-marketed tool (flagged seriously in v1); much lower exposure for an invite-only tool used personally and by a small trusted circle | Keep clear "informational, not advice" framing from day one; revisit with a lawyer only if it ever goes past a true stretch — public marketing + real strangers paying at volume |
| **Data/account security for invited users** | Real people's portfolio data, even a handful of them | Already covered by the shipped auth overhaul (v1.8.0: 2FA, session tracking, encrypted backups) — no new work needed to stay reasonably safe at this scale |

Notably absent from this table, because they don't apply at this scale/structure: funding shortfall,
competitive threats, hiring/team risk, and scalability under heavy load.

---

## 10. Milestones (Not a Roadmap)

No dates. No fixed order. Revisit whenever it feels right — quarterly is a reasonable default check-in
cadence, not a deadline.

- [ ] Use it yourself for real investing decisions for a few months — the only milestone that actually matters.
- [ ] Invite a handful of trusted people (5-20) if you want company using it.
- [ ] If someone unprompted asks "can I pay for this" — that's the real signal to build Section 7's tier, not
      before.
- [ ] If organic word of mouth pushes past what invite-only comfortably handles — revisit scaling, funded by
      whatever it's earning by then.
- [ ] Once a year (or whenever it feels relevant): re-read this plan and check it still matches reality —
      adjust the hours/week, the cost floor, and the milestones rather than treating any of this as fixed.

---

## 11. What Success Looks Like

In order — and note revenue is last, not first:

1. **You keep using it, and it keeps making your own investing decisions better.** If this alone is true a
   year from now, the project is a success, full stop.
2. **Building it stays fun.** The moment it doesn't, that's valid information, not a failure to push through.
3. **It's a strong personal engineering/portfolio project** — 1,273 tests, a real auth system, a documented
   valuation engine, a working audit tool — genuinely useful regardless of commercial outcome.
4. **A handful of other people find it useful too**, invite-only, organically — nice, not necessary.
5. **It generates some beer money, or more** — the upside case, explored at zero financial risk, never the
   reason to keep going if 1-3 stop being true.

Reversibility is a feature: because there's no funding, no team, and no paying customers owed continuity by
default, this can be paused, slowed, sped up, or shelved at any point without owing anyone an explanation.

---

## Related Documents
- [v1 strategic plan (superseded)](strategic-business-plan.md) — the earlier 2-founder/VC-scale version this
  plan replaces as the active strategy.
- [Stock Valuation Algorithm](stock_valuation_algorithm.md)
- [Portfolio Risk Assessment Algorithm](portfolio_risk_assessment_algorithm.md)
- [Architecture Overview](architecture.md)
- [CHANGELOG](../CHANGELOG.md) — the source for every claim in [Section 1](#1-what-we-actually-built-last-40-days)

---
**Document Version**: 1.0 (v2 of the strategic plan)
**Last Updated**: September 2026
**Prepared by**: Sven (with Claude)
