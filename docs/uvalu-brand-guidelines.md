# Uvalu — Brand Guidelines

> *Find value before the market does.*

---

## 1. Brand overview

**Uvalu** is a personal stock portfolio management and screening app built around a systematic, quantitative approach to identifying undervalued equities. The name is a portmanteau of *undervalued* — immediately meaningful to any value investor, yet clean and distinctive enough to stand alone as a brand.

Uvalu is not a trading app. It is a thinking tool — a rigorous, systematic layer between raw market data and investment decisions.

---

## 2. Brand positioning

| Dimension | Position |
|---|---|
| Audience | Solo investors with a systematic mindset |
| Category | Portfolio management & stock screening |
| Differentiator | Multi-model fair value engine with hard veto rules |
| Tone | Precise, confident, grounded, systematic |
| Against | Hype-driven apps, sentiment trackers, tip services |

---

## 3. Logo

### Wordmark

```
uvalu
```

- All lowercase, no capitalisation
- Tight letter-spacing: `−0.03em`
- Final **u** rendered in Signal Teal (`#1A8C6E`) — a subtle nod to the "U" in undervalued and the moment a signal surfaces
- Font weight: 500 (medium)

### Logo mark (icon)

A downward V-shape converging on a teal circle — representing a stock price finding its floor before a reversal. Clean, minimal, scalable to 16×16px.

- Icon background: Deep Navy `#0D1F3C`, border-radius 14px
- V-stroke: White `#FFFFFF`, 1.8px
- Circle at base: Mint Pulse `#1DD6A4`
- Enclosing ring: Teal `#1DD6A4`, 1.5px stroke

### Tagline

> Find value before the market does.

Use the tagline in onboarding, marketing, and the app's empty states. Never use it in dense UI contexts.

### Clear space

Maintain a minimum clear space of `1×` the height of the lowercase **u** on all sides of the logo.

### Variants

| Variant | Background | Wordmark colour | Accent colour |
|---|---|---|---|
| Dark (primary) | Deep Navy `#0D1F3C` | White `#FFFFFF` | Mint Pulse `#1DD6A4` |
| Light | Surface `#F5F7FA` | Deep Navy `#0D1F3C` | Signal Teal `#1A8C6E` |
| Monochrome | White | Deep Navy `#0D1F3C` | Deep Navy `#0D1F3C` |

### Don'ts

- Do not use all-caps or title case: ~~UVALU~~ ~~Uvalu~~
- Do not stretch, rotate, or skew the logo
- Do not place the logo on busy photographic backgrounds
- Do not change the accent colour of the final **u**
- Do not add drop shadows or gradients

---

## 4. Colour palette

### Primary colours

| Name | Hex | Usage |
|---|---|---|
| Deep Navy | `#0D1F3C` | Primary backgrounds, logo, headings, strong UI anchors |
| Signal Teal | `#1A8C6E` | Brand accent, interactive elements, links, bordered highlights |
| Mint Pulse | `#1DD6A4` | Active states, positive indicators, icon accents, badges |

### Surface colours

| Name | Hex | Usage |
|---|---|---|
| Surface White | `#F5F7FA` | App background, card surfaces |
| Positive Tint | `#E8F5F0` | Buy signals, positive metric backgrounds |
| Caution Tint | `#FDF0E8` | Monitor/watch signals, caution metric backgrounds |
| Danger Tint | `#FCEAEA` | Avoid signals, negative metric backgrounds |

### Semantic colours (data & status)

| Semantic | Hex | Use case |
|---|---|---|
| Positive text | `#0F6E56` | Positive percentage, gain, buy label |
| Caution text | `#854F0B` | Margin-of-safety warning, monitor label |
| Danger text | `#A32D2D` | Overvalued, avoid label, veto trigger |
| Muted text | `#5F5E5A` | Secondary labels, metadata |

### Colour usage rules

- Never use Deep Navy as a text colour on a dark background
- Always pair Positive/Caution/Danger tints with their matching text colour
- Data readouts (prices, ratios, percentages) use Mint Pulse or semantic text colours, never grey
- Avoid decorative use of red — reserve it strictly for avoid/veto signals

---

## 5. Typography

### Typeface

**Primary:** System sans-serif stack  
`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

**Data & numeric display:** System monospace  
`"SF Mono", "Fira Code", "Cascadia Code", monospace`

Use monospace for all ticker symbols, price values, ratios, and scores. This visually separates analytical data from prose, reinforcing the app's systematic nature.

### Type scale

| Role | Size | Weight | Line height | Usage |
|---|---|---|---|---|
| Display | 32px | 500 | 1.1 | Hero headlines, onboarding |
| Heading 1 | 24px | 500 | 1.2 | Section titles |
| Heading 2 | 18px | 500 | 1.3 | Card headings, panel labels |
| Body | 15px | 400 | 1.6 | Descriptions, explanations |
| Label | 13px | 500 | 1.4 | Field labels, metadata, badges |
| Caption | 11px | 400 | 1.5 | Footnotes, source attribution |
| Data | 14–20px | 500 | 1.2 | Prices, ratios, scores (monospace) |

### Typographic rules

- **Sentence case always.** Never title case or ALL CAPS in UI.
- **Numbers are monospace.** P/E ratios, price targets, margin of safety percentages — always monospace.
- **Tight tracking on display text.** Apply `letter-spacing: -0.02em` to headings 24px and above.
- **No mid-sentence bolding.** Bold is for headings and data labels only.

---

## 6. Iconography

Use **Tabler Icons** (outline only) throughout the UI. Never use filled variants.

| Context | Icon examples |
|---|---|
| Navigation | `ti-home`, `ti-chart-bar`, `ti-search`, `ti-bell` |
| Stock actions | `ti-plus`, `ti-star`, `ti-trash`, `ti-edit` |
| Data & analysis | `ti-trending-up`, `ti-trending-down`, `ti-calculator`, `ti-filter` |
| Status | `ti-check`, `ti-alert-triangle`, `ti-x` |
| Portfolio | `ti-briefcase`, `ti-clock`, `ti-download` |

Icon size: 20px in navigation and cards, 16px inline with text.

---

## 7. Spacing & layout

### Base unit: 4px

All spacing, padding, and margin values should be multiples of 4px.

| Token | Value | Common use |
|---|---|---|
| xs | 4px | Icon-to-text gap, tight badges |
| sm | 8px | Intra-component spacing |
| md | 12px | Card internal padding |
| lg | 16px | Section gaps, list item spacing |
| xl | 24px | Card-to-card spacing |
| 2xl | 32px | Section-to-section spacing |
| 3xl | 48px | Page-level breathing room |

### Component radius

| Element | Radius |
|---|---|
| App icon | 22px |
| Cards | 12px |
| Badges / chips | 6px |
| Buttons | 8px |
| Input fields | 8px |

### Border weight

- Card borders: `0.5px` — thin, refined, not heavy
- Dividers: `0.5px`
- Focused / selected state: `2px` (the only exception)

---

## 8. UI components

### Signal badges

Used for the buy/monitor/avoid decision output.

| Signal | Background | Text | Label |
|---|---|---|---|
| Buy | `#E8F5F0` | `#0F6E56` | BUY |
| Monitor | `#FDF0E8` | `#854F0B` | MONITOR |
| Avoid | `#FCEAEA` | `#A32D2D` | AVOID |
| Veto | `#0D1F3C` | `#FFFFFF` | VETO |

Badges use 11px uppercase text, `font-weight: 500`, horizontal padding 8px, border-radius 6px.

### Metric cards

Used to surface key valuation data at a glance.

- Background: Surface `#F5F7FA`
- Label: 11px, `#5F5E5A`, uppercase, `letter-spacing: 0.06em`
- Value: 22–28px, `font-weight: 500`, monospace, Deep Navy or semantic colour
- No border on metric cards — background contrast provides separation

### Data rows

Used in stock detail views for model outputs (DCF, P/E, Graham Number, etc.)

- Label left-aligned, 13px, muted
- Value right-aligned, 14px monospace, coloured by semantic meaning
- Divider: `0.5px` border between rows

---

## 9. Brand voice

### Principles

**Precise** — Every claim is grounded in a number. Uvalu does not use market sentiment language ("the market feels uncertain"). It uses data: "P/E of 9.4× against a fair-value estimate of 14.2×."

**Confident** — Uvalu surfaces clear signals. When the model says buy, the UI says buy. Hedging language ("you might consider") is reserved for genuinely ambiguous cases, not the default tone.

**Systematic** — The algorithm decides, not the mood. Copy reinforces that the process is repeatable, rule-based, and unemotional.

**Grounded** — No hype. No FOMO. No "hot picks." Uvalu respects the user's intelligence and long-term orientation.

### Voice examples

| Context | Do | Don't |
|---|---|---|
| Empty state | "No stocks match your screening criteria." | "Looks like nothing's here yet! 🙁" |
| Buy signal | "Uvalu assigns a BUY signal. Composite score: 82/100. Margin of safety: 34%." | "This stock looks great — might be worth a look!" |
| Veto trigger | "Hard veto triggered: debt/equity exceeds threshold. Stock excluded from scoring." | "We had to remove this one from the results." |
| Onboarding | "Uvalu evaluates fair value across six models and surfaces stocks with a sufficient margin of safety." | "Welcome! Let's get started on your investment journey 🚀" |

### Writing rules

- No emoji in core UI
- No exclamation marks in data contexts
- Use "Uvalu" (not "we" or "the app") when describing the system's actions
- Numeric values always include units: `34%`, `11.4×`, `€42.80`
- Percentages use `%`, multiples use `×`, currency symbols precede the value

---

## 10. App icon

### Specifications

| Platform | Size | Format | Radius |
|---|---|---|---|
| iOS | 1024×1024px | PNG | Applied by OS |
| Android | 512×512px | PNG | 22.37% of canvas |
| Favicon | 32×32px | ICO / SVG | — |
| Web manifest | 192×192px, 512×512px | PNG | — |

### Construction

- Background: Deep Navy `#0D1F3C`, full bleed
- Icon mark centred, occupying ~55% of canvas width
- V-stroke: White, line cap round
- Base circle: Mint Pulse `#1DD6A4`
- No text in the app icon

---

## 11. What Uvalu is not

Uvalu's identity is defined as much by what it rejects as what it embraces.

- Not a social trading app — no feeds, no following, no tips from strangers
- Not a robo-advisor — it surfaces signals, not recommendations; the user decides
- Not a dashboard for casual trackers — every screen serves the valuation process
- Not gamified — no streaks, no confetti, no engagement mechanics
- Not short-term — the entire system is oriented around intrinsic value and long-duration holding

---

*Document version 1.0 — Uvalu Brand Guidelines*
