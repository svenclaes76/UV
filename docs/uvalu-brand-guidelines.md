# Uvalu — Brand Guidelines

> *Find value before the market does.*

---

## 1. Brand overview

**Uvalu** is a personal stock portfolio management and screening app built around a systematic, quantitative approach to identifying undervalued equities. The name is a portmanteau of *undervalued* — immediately meaningful to any value investor, yet clean and distinctive enough to stand alone as a brand.

Uvalu is not a trading app. It is a thinking tool — a rigorous, systematic layer between raw market data and investment decisions. Its signals are model outputs based on public data, the same for every user; they are not personal investment advice.

---

## 2. Brand positioning

| Dimension | Position |
|---|---|
| Audience | Solo investors with a systematic mindset |
| Category | Portfolio management & stock screening |
| Differentiator | Multi-model fair value engine with quality screens |
| Tone | Precise, confident, grounded, systematic |
| Against | Hype-driven apps, sentiment trackers, tip services |

---

## 3. Logo

### Wordmark

```
uvalu
```

- All lowercase, no capitalisation — **in the wordmark only**. In running text the name is written *Uvalu* (see §9).
- Tight letter-spacing: `−0.03em`
- Final **u** rendered in Signal Teal (`#1A8C6E`) — a subtle nod to the "U" in undervalued and the moment a signal surfaces
- Font weight: 500 (medium)

### Logo mark (icon)

A downward V-shape converging on a teal circle — representing a stock price finding its floor before a reversal. Clean, minimal, scalable to 16×16px.

- Icon background: Deep Navy `#0D1F3C`, border-radius 14px
- V-stroke: White `#FFFFFF`, 1.8px
- Circle at base: Mint Pulse `#1DD6A4`
- Enclosing ring: Mint Pulse `#1DD6A4`, 1.5px stroke

### Tagline

> Find value before the market does.

Use the tagline in onboarding, the sign-in screen, marketing, and the app's empty states. Never in dense UI contexts, and never next to a specific stock, signal or number — it describes the approach, not a result.

### Clear space

Maintain a minimum clear space of `1×` the height of the lowercase **u** on all sides of the logo.

### Variants

| Variant | Background | Wordmark colour | Accent colour |
|---|---|---|---|
| Dark (primary) | Deep Navy `#0D1F3C` | White `#FFFFFF` | Mint Pulse `#1DD6A4` |
| Light | Surface `#F5F7FA` | Deep Navy `#0D1F3C` | Signal Teal `#1A8C6E` |
| Monochrome | White | Deep Navy `#0D1F3C` | Deep Navy `#0D1F3C` |

### Don'ts

- Do not set the wordmark in all-caps or title case: ~~UVALU~~ ~~Uvalu~~ (as a logo)
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

### Surface colours (light theme)

| Name | Hex | Usage |
|---|---|---|
| Page | `#EAEEF3` | App page background |
| Surface White | `#F5F7FA` | Inset panels, card footers, inputs |
| Panel | `#FFFFFF` | Cards |
| Positive Tint | `#E8F5F0` | Undervalued signal, positive metric backgrounds |
| Caution Tint | `#FDF0E8` | Neutral signal, caution metric backgrounds |
| Danger Tint | `#FCEAEA` | Low-score signal, negative metric backgrounds |

### Semantic colours (data & status)

| Semantic | Hex | Use case |
|---|---|---|
| Positive text | `#0F6E56` | Positive percentage, gain, Undervalued label |
| Caution text | `#854F0B` | Margin-of-safety warning, Neutral label |
| Caution fill | `#C98A3A` | Bars and swatches for caution states, e.g. a price above the model fair value |
| Danger text | `#A32D2D` | Negative values, Low-score label, failed quality screen |
| Muted text | `#5F5E5A` | Secondary labels, metadata |

### Dark theme

The app has a full dark variant. Use these values (CSS tokens in `uvalu/styles.py`) instead of inventing new shades.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0A1730` | `#EAEEF3` | Page background |
| `--panel` | `#0E2143` | `#FFFFFF` | Cards |
| `--panel-2` | `#0B1D3D` | `#F5F7FA` | Inset panels, card footers |
| `--text` | `#F5F7FA` | `#0D1F3C` | Body text |
| `--muted` | `rgba(245,247,250,0.55)` | `#5F5E5A` | Secondary text, metadata (≥ 4.5:1 on both themes) |
| `--faint` | `rgba(245,247,250,0.30)` | `rgba(13,31,60,0.38)` | Decoration only — never for text that must be read |
| `--line` | `rgba(255,255,255,0.08)` | `rgba(13,31,60,0.10)` | Card borders, dividers |
| `--up-txt` | `#1DD6A4` | `#0F6E56` | Gains, Undervalued |
| `--down-txt` | `#F0A6A6` | `#A32D2D` | Losses, Low score |
| `--amber-txt` | `#E0B94D` | `#854F0B` | Caution text |
| `--amber-fill` | `#C98A3A` | `#C98A3A` | Caution bars and swatches |

### Colour usage rules

- Never use Deep Navy as a text colour on a dark background
- Always pair Positive/Caution/Danger tints with their matching text colour
- Data readouts (prices, ratios, percentages) use Mint Pulse or semantic text colours, never grey. **Exception:** metadata values — times, dates, model and app versions — are muted, because they describe a value rather than being one.
- Avoid decorative use of red — reserve it for negative values, the Low-score signal and a failed quality screen. Caution states (a price above fair value, a concentration warning) are amber, not red.
- Tints are for signals and metrics, never decoration: no mint or tinted panels around metadata.
- Text that must be read is at least 4.5:1 against its background; use `--muted`, never `--faint`.

---

## 5. Typography

### Typeface

**Primary:** System sans-serif stack  
`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

**Data & numeric display:** System monospace  
`"SF Mono", "Fira Code", "Cascadia Code", monospace`

Use monospace for all ticker symbols, price values, ratios, scores, times and version numbers. This visually separates analytical data from prose, reinforcing the app's systematic nature.

### Type scale

| Role | Size | Weight | Line height | Usage |
|---|---|---|---|---|
| Display | 32px | 500 | 1.1 | Hero headlines, onboarding |
| Heading 1 | 24px | 500 | 1.2 | Page titles |
| Document title | 20px | 500 | 1.25 | Title of a legal document inside its card |
| Heading 2 | 17–18px | 500 | 1.3 | Sections in long text (17px), panel headings (18px) |
| Card heading | 15px | 500 | 1.3 | Card header rows |
| Body | 15px | 400 | 1.6 | Descriptions, explanations |
| Long-form body | 14px | 400 | 1.65 | Legal texts, methodology, release notes; measure 72ch |
| Data-screen text | 13–13.5px | 400 | 1.5 | Rows and descriptions on data screens |
| Label | 13px | 500 | 1.4 | Field labels, metadata, badges |
| Caption | 12px | 400 | 1.5 | Footnotes, provenance, source attribution (muted) |
| Data | 14–20px | 500 | 1.2 | Prices, ratios, scores (monospace) |

### Typographic rules

- **Sentence case** for headings, buttons, badges, links and prose. Never title case.
- **Small labels are uppercase.** Compact column headers, filter labels and metric-card labels (10–11px) use uppercase with `letter-spacing: 0.06em`, muted colour. This is the only place for capitals: never at 12px or larger, and never for headings or buttons.
- **Numbers are monospace.** P/E ratios, price targets, margin of safety percentages — always monospace.
- **Tight tracking on display text.** Apply `letter-spacing: -0.02em` to headings 24px and above.
- **No mid-sentence bolding.** Bold is for headings and data labels only.

---

## 6. Iconography

Use **Material Symbols (outlined)** everywhere — in the app (Streamlit renders them natively as `:material/name:`) and in marketing material — so one icon style runs through every surface. Outline only, never filled variants. *(Replaces Tabler Icons from v1.0.)*

| Context | Icon examples (Material) |
|---|---|
| Navigation | `dashboard`, `search`, `star`, `business_center`, `monitoring` |
| Stock actions | `add`, `star`, `delete`, `edit` |
| Data & analysis | `trending_up`, `trending_down`, `calculate`, `filter_list` |
| Status | `check`, `warning`, `close`, `info` |
| Portfolio & app | `refresh`, `schedule`, `download`, `settings`, `help` |

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
| Tooltips | 8px |

### Border weight

- Card borders: `0.5px` — thin, refined, not heavy
- Dividers: `0.5px`
- Focused / selected state: `2px` (the only exception)

### Page layouts

**Data screens** (Dashboard, Portfolio, Risk, Screener, Watchlist): full content width. Page header = title (22–24px), subtitle (13px muted) and, on screens with signals, the provenance line (§8) as the third line. Actions sit right-aligned on the title row.

**Supporting pages** (Settings, Methodology & help, Legal, About) share one frame:

- Left-aligned on the page gutter, max width 1180px.
- Back link above the title: "← Back to {page}", 12px muted, to the page the user came from (the Dashboard otherwise).
- Title 24px / 500 / −0.02em (Heading 1), optional 13px muted subtitle 4px below, 20px gap to the content.
- Two columns: a **200px sticky section list** and a content column of at most **760px**, 32px apart.
- Section list: 13px items. The current item has a 2px teal left border, panel background and weight 500; the others are muted. An optional "On this page" list follows in 12px with a 0.5px left rule.
- Content in white cards (12px radius, 0.5px border), sentence-case 15px card headers, long-form text at 14px / 1.65 within 72ch.
- Below 768px the section list is hidden; Legal shows a document picker instead.

---

## 8. UI components

### Signal badges

The model's signal for a stock. Badges describe the model output; they never tell the user to buy or sell.

| Signal | Background | Text | Label |
|---|---|---|---|
| Undervalued | `#E8F5F0` | `#0F6E56` | Undervalued |
| Neutral | `#FDF0E8` | `#854F0B` | Neutral |
| Low score | `#FCEAEA` | `#A32D2D` | Low score |
| Fails quality screen | `#0D1F3C` | `#FFFFFF` | Fails quality screen |
| No signal | grey tint | Muted | No signal |

- Sentence case, 10.5–11px, `font-weight: 500`, horizontal padding 8–9px, border-radius 6px.
- Every signal badge carries the methodology tooltip: *"Model output based on public data and the settings shown. Not a recommendation tailored to you. See Methodology for thresholds."*
- In dark theme the tints become translucent (`--up-bg`, `--amber-bg`, `--down-bg`); Fails quality screen is `#1E2D4A` with a light hairline.

### Signal provenance line

Wherever signals are listed (Dashboard holdings, Screener, Watchlist) or shown for one stock (stock drawer, Analysis), say when they were made. This line is a legal requirement and must stay **visible next to the signals** — never move it into a tooltip or popover.

> Signals computed `7 Oct 2026 21:15` · prices delayed, as of `19:37` · model `M1` · Methodology →

- Placement: the third line of the page header, directly under the subtitle; in the drawer and Analysis 8px under the ticker line.
- Style: 12px muted caption, no fill, no border. Values monospace 11.5px muted. Separators `·` in a faint tone.
- Each fact wraps as a whole, never mid-phrase.
- Prices are always labelled **delayed**.
- An amber chip ("⚠ oldest 3 weeks") appears when any price is more than 72 hours old.
- Ends with the quiet **Methodology →** link.
- On the Screener, the share of covered stocks per signal is shown in the signal filter pills (`Undervalued 3%`), with the note "share of covered stocks".

### Links

| Kind | Style | Example |
|---|---|---|
| Call to action | Signal Teal, no underline, ends with "→" | Full analysis → |
| Quiet link | Muted text, underlined in the line colour (offset 3px), text colour on hover, ends with "→" | Methodology → |

A link always ends with "→", so it reads as a link even in grey. Back links start with "←".

### Tooltips

One style for every tooltip: the app's own (`title` attributes, drawn by `uvalu/tooltips.py`), Streamlit's help icons and chart hover labels.

| | Light theme | Dark theme |
|---|---|---|
| Background | `#FFFFFF` | `#15305A` |
| Text | `#0D1F3C` | `#F5F7FA` |
| Border | 0.5px `rgba(13,31,60,0.14)` | 0.5px `rgba(245,247,250,0.16)` |
| Shadow | `0 4px 16px rgba(13,31,60,0.12)` | `0 4px 16px rgba(0,0,0,0.45)` |

- 12px / 1.5 sans text, padding 6px 10px, 8px radius, max width 280px.
- Never a dark box on a light page, never a trace or brand colour as the fill.
- Tooltips add detail; anything the user must see (provenance, disclaimers, risk notes) stays on the page.

### Metric cards

Used to surface key valuation data at a glance.

- Background: Panel, with a `0.5px` border on the page background
- Label: 10–11px, muted, uppercase, `letter-spacing: 0.06em` (§5 small labels)
- Value: 22–28px, `font-weight: 500`, monospace, Deep Navy or semantic colour

### Data rows

Used in stock detail views for model outputs (Graham Number, P/E fair value, EPV, DDM, …) and for key/value lists such as the About page's build details.

- Label left-aligned, 13px, muted
- Value 13–14px monospace, coloured by semantic meaning; right-aligned in tables, left-aligned in key/value lists
- Divider: `0.5px` border between rows

### Fair-value ladder

- The bar fills from zero to the current price; a dashed tick marks the model fair value.
- Fill colours: Mint when the price is below fair value, Teal within ±3%, Caution fill `#C98A3A` above it.
- Legend on the table card's title row: "Below / Near / Above model fair value · Model fair value", 11.5px muted.

### Disclosures

These texts are required and keep their wording; translations must keep their meaning.

| Element | Where | Wording / style |
|---|---|---|
| Beta banner | Top of every screen | "Free beta: a test version. Features and data can change, and the beta can end at any time." Mint tint, small text |
| Footer disclaimer | Bottom of every screen | "Uvalu is an analysis tool. Scores, fair values and signals are model outputs based on public data and are the same for every user. They are not personal investment advice…" + producer + links to the legal pages |
| Founder notice | Stock drawer and Analysis, when the founder holds the stock | "Disclosure: the founder of Uvalu holds a position in this stock. Its signal is calculated exactly like every other stock's." 12px muted |
| Badge tooltip | Every signal badge | See Signal badges |

---

## 9. Brand voice

### Principles

**Precise** — Every claim is grounded in a number. Uvalu does not use market sentiment language ("the market feels uncertain"). It uses data: "P/E of 9.4× against a fair-value estimate of 14.2×."

**Clear, not directive** — Uvalu states what the models found, plainly and without hedging the facts. It never tells the user what to do: no "buy", "sell", "you should", and no language that turns a signal into a recommendation. The user decides.

**Systematic** — The rules decide, not the mood. Copy reinforces that the process is repeatable, rule-based, and unemotional.

**Grounded** — No hype. No FOMO. No "hot picks". No promises about returns or beating the market. Uvalu respects the user's intelligence and long-term orientation.

### Voice examples

| Context | Do | Don't |
|---|---|---|
| Empty state | "No stocks match your screening criteria." | "Looks like nothing's here yet! 🙁" |
| Model signal | "Model signal: Undervalued. Composite score 82/100, margin of safety 34%." | "Uvalu assigns a BUY signal." / "This stock looks great — might be worth a look!" |
| Quality screen | "Fails quality screen: debt/equity of 240% exceeds the 200% limit. Composite score set to 0." | "Hard veto triggered. Stock excluded." / "We had to remove this one from the results." |
| Onboarding | "Uvalu values each stock with several models and shows how far the price is from the model fair value." | "Welcome! Let's get started on your investment journey 🚀" |
| Risk | "Model outputs can be wrong. Share prices can stay below or above fair value for years." | "Find bargains before everyone else." |

### Words to use and avoid

| Use | Avoid |
|---|---|
| Undervalued, Neutral, Low score, Fails quality screen | Buy, Monitor, Avoid, Veto (as signal names) |
| quality screen, quality rule | hard veto |
| model fair value, model estimate | true value, target price |
| signal, model output | recommendation, advice, pick, tip |
| delayed price | live price, real-time (during the beta) |

### Writing rules

- No emoji in core UI
- No exclamation marks in data contexts
- In the product, use "Uvalu" (not "we" or "the app") when describing the system's actions. Legal texts (terms, privacy, policies) use "we" for the operator.
- Numeric values always include units: `34%`, `11.4×`, `€42.80`
- Percentages use `%`, multiples use `×`, currency symbols follow the user's region format

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
- Not a robo-advisor or investment adviser — it shows model signals, not recommendations; the user decides
- Not a broker — no orders, no custody
- Not a dashboard for casual trackers — every screen serves the valuation process
- Not gamified — no streaks, no confetti, no engagement mechanics
- Not short-term — the entire system is oriented around intrinsic value and long-duration holding

---

## Changes

**v1.2 — 7 Oct 2026**

- Uppercase small labels confirmed as the rule for 10–11px column headers, filter and metric labels (no longer "under review").
- Icons: Material Symbols (outlined) everywhere, marketing included; Tabler dropped.
- Tagline kept; usage guidance restored, with the rule never to place it next to a specific stock, signal or number.

**v1.1 — 7 Oct 2026** (matches app v2026.10.2)

- Signal badges renamed to the legal wording (Undervalued / Neutral / Low score / Fails quality screen / No signal), sentence case; "hard veto" → "quality screen"; voice principles and examples no longer present signals as buy instructions; tagline flagged for legal review (decided in v1.2).
- Added: dark-theme tokens, caution fill `#C98A3A`, signal provenance line, links, tooltips, fair-value ladder, disclosures, supporting-page layout.
- Typography: long-form body 14px, 17px section headings, 12px captions; the uppercase small-label exception made explicit.
- Fixed: wordmark-vs-name rule, "we" in legal texts, logo ring colour, icon set (Material Symbols), no DCF in the model list.

*Document version 1.2 — Uvalu Brand Guidelines*
