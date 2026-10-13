# Expert Profile: Accessibility Specialist

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Medium–High — determine applicability early; audit before launch

---

## Why Uvalu needs this expert

The **European Accessibility Act** (Directive 2019/882, applicable since 28 June 2025, transposed in Belgium) covers certain consumer-facing digital services, including e-commerce and consumer banking services. Whether and how it applies to a subscription investment tool — and whether the micro-enterprise exemption for service providers applies to Uvalu — needs an expert answer. Independently of the legal obligation, Uvalu's dense tables, charts, colour-coded signals and dark/light themes carry real accessibility risks for users with low vision, colour blindness or who use screen readers or keyboards.

## Required expertise

- Certified accessibility professional (e.g. **IAAP CPACC / WAS / CPWA**) or equivalent track record
- Expert knowledge of **WCAG 2.1 / 2.2 Level AA** and **EN 301 549** (the European harmonised standard)
- Working knowledge of the **European Accessibility Act**, its Belgian transposition, scope, exemptions and the required accessibility statement
- Hands-on testing with assistive technology: NVDA, JAWS, VoiceOver, keyboard-only, zoom/magnification
- Experience with **data-heavy applications**: accessible tables, charts, colour-independent status indicators
- Familiarity with **Streamlit** limitations and workarounds for custom components and injected CSS

## Scope of review

1. **Applicability:** does the EAA apply to Uvalu; does the micro-enterprise exemption apply now, and what changes as the business grows
2. **Colour and contrast:** Deep Navy / Signal Teal / Mint Pulse palette in light and dark mode; signal badges must not rely on colour alone
3. **Charts and visualisations:** text alternatives, data tables, accessible tooltips
4. **Tables and Screener:** headers, sorting, keyboard navigation, screen-reader output
5. **Forms and authentication:** login, 2FA, passkeys, error messages, focus management
6. **Navigation shell:** landmarks, headings, skip links, focus order
7. **Language attributes** across the six languages
8. **Accessibility statement** and feedback mechanism
9. **Design system:** accessibility rules built into the design tokens and the shared components in `uvalu/components.py` so new screens stay compliant

## Expected deliverables

- Opinion on EAA applicability and obligations (coordinated with a lawyer if needed)
- WCAG 2.2 AA / EN 301 549 audit report with severity-rated issues per screen
- Concrete fixes for shared components and design tokens
- Accessibility statement draft
- Retest after fixes
- Checklist for future development

## Material to prepare

- Staging environment with test accounts
- Brand guidelines v1.5 (`docs/uvalu-brand-guidelines.md`) and design tokens (light/dark)
- Redesign screens and the "Consensus" logo usage
- Company size and turnover expectations (for exemption analysis)

## Questions to ask when selecting

- Have you audited data-heavy dashboards or trading/investing apps?
- Do you test with real assistive technology rather than only automated tools?
- Can you advise on EAA scope and exemptions, or do you work with a lawyer for that?

## Red flags

- Relies only on automated scanners (they catch a minority of issues)
- No knowledge of EN 301 549 or the EAA
- Recommends accessibility overlay widgets as a solution

## Where to find

- IAAP member directory
- Belgian accessibility organisations and Anysurfer-certified auditors
- Accessibility consultancies with fintech or banking clients
