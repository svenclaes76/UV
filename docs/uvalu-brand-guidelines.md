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

The logo is the **Consensus** mark plus the wordmark (decided 11 Oct 2026; specification: `docs/design/logo-consensus-spec.md`). Never redraw or recolour a mark by hand: use the files in `assets/logo/`, which `tools/build_logo.py` generates from the specification. The app shows the lockup through `uvalu/logo.py`.

### Logo mark

Two overlapping rings with a filled lens where they meet. Each ring is an independent valuation model; the lens is where the models agree, and that zone of agreement is where Uvalu finds value. The mark shows Uvalu's method, not a general idea of value.

- **Rings, outlined:** the models are tools, kept open and visible, never black boxes.
- **Lens, filled with mint or teal:** the only filled shape. It is the result, the part that matters.
- **Plain geometry:** symmetric, precise and calm; no arrows, charts or growth clichés.

Two weights, both on a 64 × 64 grid. The lens is drawn first, the rings are stroked on top.

| Property | Main mark | Small mark |
|---|---|---|
| Use at | larger than 32px | 32px and below |
| Ring radius | 17 | 18 |
| Ring centres (x, y) | (22, 32) and (42, 32) | (24, 32) and (40, 32) |
| Ring stroke | 4.5 | 5.5 |
| Visible lens width | about 9.5 | about 14.5 |

### Wordmark

```
uvalu
```

- All lowercase, no capitalisation — **in the wordmark only**. In running text the name is written *Uvalu* (see §9); screen readers get "Uvalu" (`aria-label`).
- Inter, weight 500, letter-spacing `−0.03em`, final **u** in the accent colour.
- The wordmark is artwork, not live text: the files and the app use outlined Inter (no font is loaded), so it renders the same on every system.

### Lockup

Mark plus wordmark, every dimension derived from the mark height H:

| Element | Spec | At H = 64px |
|---|---|---|
| Font size | 0.875 × H | 56px |
| Gap, mark to wordmark | 0.1875 × H | 12px |
| Vertical alignment | x-height centred on the mark's centre line | baseline at about 47px |
| Clear space | the height of the lowercase u on all sides | about 31px |

The minimum size is 16px for the mark alone and a 24px mark height for the lockup.

### Colour variants

Each variant uses exactly two inks on its ground. Dark is the primary variant.

| Variant | Ground | Rings and wordmark | Lens and final u |
|---|---|---|---|
| Dark (primary) | Deep Navy `#0D1F3C` | White `#FFFFFF` | Mint Pulse `#1DD6A4` |
| Light | White `#FFFFFF` or Surface `#F5F7FA` | Deep Navy `#0D1F3C` | Signal Teal `#1A8C6E` |
| Monochrome | White or transparent | Black `#000000` | Black `#000000` |

Mint is never used for the lens on a light ground (below 2:1). For one-colour reversed use, make every ink white.

### Usage by size

Rendered at 32px or smaller, use the small mark; larger, the main mark.

| Context | Mark | Variant | Rendered size |
|---|---|---|---|
| Browser tab icon | Small, on a tile | Dark | 16 and 32px |
| App top bar | Main, in the lockup | Follows the theme: light lockup in the light theme, dark in the dark theme (`--logo-ring`, `--logo-accent`) | mark height 26px, 13px to the "value engine" tag |
| Admin portal sidebar | Main, in the lockup | Dark (the portal is dark only) | mark height 24px, 12px to the "admin" tag |
| Sign-in and onboarding | Main, in the lockup | Dark (navy panel) | mark height 48px, 23px to the tag |
| App and PWA icons | Main, on a tile | Dark | 180, 192 and 512px |
| Social and Open Graph image | Main, in the lockup | Dark on navy | mark height about 120px on 1200 × 630 |
| Print, embossing, one colour | Main or small, by size | Monochrome | — |

### Tagline

> Find value before the market does.

Use the tagline in onboarding, the sign-in screen, marketing, and the app's empty states. Never in dense UI contexts, and never next to a specific stock, signal or number — it describes the approach, not a result.

### Don'ts

- Do not recolour the rings and lens separately, add gradients or shadows, or outline the lens.
- Do not change the overlap, stroke weights or proportions, or mix main-mark rings with the small-mark lens.
- Do not use mint on a light ground, or put the dark variant straight onto white.
- Do not stretch, rotate or skew the mark, or move the accent away from the final u.
- Do not set the wordmark in all-caps or title case: ~~UVALU~~ ~~Uvalu~~ (as a logo), or as live text.
- Do not place the logo on busy photographic backgrounds.

---

## 4. Colour palette

### Primary colours

| Name | Hex | Usage |
|---|---|---|
| Deep Navy | `#0D1F3C` | Primary backgrounds, logo, headings, strong UI anchors |
| Signal Teal | `#1A8C6E` | Brand accent, fills, borders, selected states, focus ring in light theme. Not for small text: it is 4.2:1 on white, so links use `--link` |
| Mint Pulse | `#1DD6A4` | Active states, positive indicators and data in dark theme, icon accents. Never text on a light background (1.7:1) |

### Surface colours (light theme)

| Name | Hex | Usage |
|---|---|---|
| Page | `#EAEEF3` | App page background |
| Surface White | `#F5F7FA` | Inset panels, card footers, inputs |
| Panel | `#FFFFFF` | Cards |
| Positive Tint | `#E8F5F0` | Undervalued signal, positive metric backgrounds |
| Caution Tint | `#FDF0E8` | Neutral signal, caution metric backgrounds |
| Danger Tint | `#FCEAEA` | Low-score signal, negative metric backgrounds |

In the app the Positive and Danger tints are the translucent tokens `--up-bg` and `--down-bg` (see Dark theme), which read as these tints on a white panel. Use the hex values only where transparency isn't available, e.g. in email or print.

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
| `--tile` | `#0B1D3D` | `#F5F7FA` | Inset tiles inside cards |
| `--line` | `rgba(255,255,255,0.08)` | `rgba(13,31,60,0.10)` | Card borders, dividers |
| `--line-2` | `rgba(255,255,255,0.05)` | `rgba(13,31,60,0.06)` | Row dividers inside a card |
| `--teal` | `#1A8C6E` | `#1A8C6E` | Accent fills, borders, selected states |
| `--mint` | `#1DD6A4` | `#1DD6A4` | Accent in dark theme, logo |
| `--link` | `#3FBF98` | `#167A60` | Link text (6.9:1 on dark panel, 5.3:1 on white) |
| `--logo-ring` | `#FFFFFF` | `#0D1F3C` | Top-bar logo: rings and wordmark (§3) |
| `--logo-accent` | `#1DD6A4` | `#1A8C6E` | Top-bar logo: lens and final u (§3) |
| `--soft` | `rgba(29,214,164,0.05)` | `rgba(29,214,164,0.055)` | Hover and selected rows, system notices (beta banner) |
| `--up-txt` | `#1DD6A4` | `#0F6E56` | Gains, Undervalued |
| `--up-bg` | `rgba(29,214,164,0.14)` | `rgba(15,110,86,0.11)` | Undervalued badge, positive metric background |
| `--down-txt` | `#F0A6A6` | `#A32D2D` | Losses, Low score |
| `--down-bg` | `rgba(163,45,45,0.26)` | `rgba(163,45,45,0.11)` | Low-score badge, negative metric background |
| `--amber-txt` | `#E0B94D` | `#854F0B` | Caution text |
| `--amber-bg` | `rgba(214,158,29,0.16)` | `#FDF0E8` | Neutral badge, caution background |
| `--amber-fill` | `#C98A3A` | `#C98A3A` | Caution bars and swatches |
| `--uv-track` | `rgba(245,247,250,0.10)` | `#EEF1F5` | Empty part of bars and meters |
| `--grid` | `rgba(255,255,255,0.06)` | `rgba(13,31,60,0.08)` | Chart gridlines |
| `--axis` | `rgba(245,247,250,0.5)` | `#5F5E5A` | Chart axes and tick labels, neutral bar fill |
| `--shadow` | `0 1px 2px rgba(0,0,0,0.4)` | `0 1px 3px rgba(13,31,60,0.08)` | Cards |
| `--tip-bg` / `--tip-border` / `--tip-shadow` | see Tooltips | see Tooltips | Tooltips |

### Colour usage rules

- Never use Deep Navy as a text colour on a dark background
- Always pair Positive/Caution/Danger tints with their matching text colour
- Data readouts (prices, ratios, percentages) use `--text` or the semantic text colours (`--up-txt`, which is Mint Pulse in dark theme), never grey. **Exception:** metadata values — times, dates, model and app versions — are muted, because they describe a value rather than being one.
- Avoid decorative use of red — reserve it for negative values, the Low-score signal and a failed quality screen. Caution states (a price above fair value, a concentration warning) are amber, not red.
- Tints are for signals and metrics, never decoration: no mint or tinted panels around metadata. The one exception is `--soft`, a near-invisible mint wash kept for hover and selected rows and for system notices such as the beta banner.
- Text that must be read is at least 4.5:1 against its background; use `--muted`, never `--faint`.
- Graphics that carry meaning (bars, chart marks, focus rings, icons without a label) are at least 3:1 against their background.

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
| Label | 13px | 500 | 1.4 | Field labels, metadata (badges: see §8) |
| Caption | 12px | 400 | 1.5 | Footnotes, provenance, source attribution (muted) |
| Data | 14–20px | 500 | 1.2 | Prices, ratios, scores (monospace) |

### Typographic rules

- **Sentence case** for headings, buttons, badges, links and prose. Never title case.
- **Small labels are uppercase.** Compact column headers, filter labels and metric-card labels (10–11px) use uppercase with `letter-spacing: 0.06em`, muted colour. This is the only place for capitals: never at 12px or larger, and never for headings or buttons.
- **Numbers are monospace.** P/E ratios, price targets, margin of safety percentages — always monospace.
- **Tight tracking on display text.** Apply `letter-spacing: -0.02em` to headings 24px and above.
- **No mid-sentence bolding.** Bold is for headings and data labels only.

### Other languages

The app ships in six languages. Type has to hold in all of them:

- Sentence case follows each language's own rules, e.g. German nouns keep their capital.
- Uppercase small labels come from CSS (`text-transform`), never from uppercase strings in the translation files.
- Allow about 30% text expansion (German, Dutch). Buttons, badges, pills and column headers size to their content. Never give them a fixed width that only fits English.
- A label that doesn't fit wraps or truncates with a tooltip. It never shrinks below the type scale.

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

Icon size: 16px in the top navigation and inline with text, 20px in cards (the app and the design reference use 16px navigation icons, decided 9 Oct 2026).

---

## 7. Spacing & layout

### Base unit: 4px

Layout spacing (gaps, margins, card padding) uses multiples of 4px. Inside small components (badge and tooltip padding, underline offsets) 1–2px optical adjustments are allowed, e.g. tooltip padding 6px 10px.

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
| Cards | 12px |
| Buttons, inputs, tooltips, banners, inset tiles | 8px |
| Badges / chips / pills | 6px |
| Inline delta chips (metric deltas) | 4px |
| Dots, rings, avatars | 50% |

Only these values. The app icon and logo mark use a ratio instead (§10). Any 7, 9 or 10px radius in the code is legacy and should be rounded to the nearest value above.

### Border weight

- Card borders: `0.5px` — thin, refined, not heavy
- Dividers: `0.5px`
- Focused / selected state: `2px`. This covers the focus ring, the current item in a section list and a selected pill. It is the only heavier border.

### Focus

- Keyboard focus (`:focus-visible` only, not on mouse click): 2px solid outline, offset 2px, in `--teal` (light theme) or `--mint` (dark theme), following the element's radius.
- Never remove a focus outline without replacing it.

### Elevation

- Cards: `--shadow` (a 1–3px soft shadow) plus the 0.5px border.
- Tooltips and popovers: `--tip-shadow`.
- Nothing else casts a shadow. The logo never does (§3).

### Loading

- No data yet: skeleton bars with the `uvShimmer` sweep, shaped and placed like the content they stand in for, so nothing jumps when data arrives.
- Data shown but refreshing: keep the old values on screen with a small spinner or the mint `uvRing` pulse beside the provenance line. Never blank the page for a refresh.
- New content fades in (`uvFadeIn`). No other motion; respect `prefers-reduced-motion`.

### Page layouts

**Data screens** (Dashboard, Portfolio, Risk, Screener, Watchlist): full content width. Page header = title (Heading 1, 24px), subtitle (13px muted) and, on screens with signals, the provenance line (§8) as the third line. Actions sit right-aligned on the title row.

**Supporting pages** (Settings, Methodology, Legal, About) share one frame:

- Left-aligned on the page gutter, max width 1180px.
- Back link above the title: "← Back to {page}", 12px muted, to the page the user came from (the Dashboard otherwise).
- Title 24px / 500 / −0.02em (Heading 1), optional 13px muted subtitle 4px below, 20px gap to the content.
- Two columns: a **200px sticky section list** and a content column of at most **760px**, 32px apart.
- Section list: 13px items. The current item has a 2px teal left border, panel background and weight 500; the others are muted. An optional "On this page" list follows in 12px with a 0.5px left rule.
- Content in white cards (12px radius, 0.5px border), sentence-case 15px card headers, long-form text at 14px / 1.65 within 72ch.
- Below 768px the section list is hidden; Legal shows a document picker instead.

**Phone layout** (below 768px) is not designed yet; it's on the backlog. Until then: one column, cards full width with a 16px gutter, and wide tables scroll sideways inside their card, never the page. The provenance line and disclosures stay visible at every width.

---

## 8. UI components

### Signal badges

The model's signal for a stock. Badges describe the model output; they never tell the user to buy or sell.

| Signal | Background | Text | Label |
|---|---|---|---|
| Undervalued | `--up-bg` | `--up-txt` | Undervalued |
| Neutral | `--amber-bg` | `--amber-txt` | Neutral |
| Low score | `--down-bg` | `--down-txt` | Low score |
| Fails quality screen | `#0D1F3C` | `#FFFFFF` | Fails quality screen |
| No signal | `rgba(128,128,128,0.15)` light, `rgba(245,247,250,0.07)` dark | `--muted` | No signal (the peer group needed to rank the stock isn't available yet) |
| No data | same as No signal | `--muted` | No data (no scored data for the row at all) |

- Sentence case, 10.5–11px, `font-weight: 500`, horizontal padding 8–9px, border-radius 6px.
- Every signal badge carries the methodology tooltip: *"Model output based on public data and the settings shown. Not a recommendation tailored to you. See Methodology for thresholds."*
- In dark theme Fails quality screen is `#1E2D4A` with a light hairline; the other badges follow their tokens.

### Signal provenance line

Wherever signals are listed (Dashboard holdings, Screener, Watchlist) or shown for one stock (stock drawer, Analysis), say when they were made. This line is a legal requirement and must stay **visible next to the signals** — never move it into a tooltip or popover.

> Signals computed `7 Oct 2026 21:15` · prices delayed, as of `19:37` · model `M1` · Methodology →

- Placement: the third line of the page header, directly under the subtitle; in the drawer and Analysis 8px under the ticker line.
- Style: 12px muted caption, no fill, no border. Values monospace 11.5px muted. Separators `·` in a faint tone.
- Each fact wraps as a whole, never mid-phrase.
- Prices are always labelled **delayed**.
- An amber chip (`warning` symbol + "oldest 3 weeks") appears when any price is more than 72 hours old.
- Ends with the **Methodology →** link, in the link colour (`--link`).
- On the Screener, the share of covered stocks per signal is shown in the signal filter pills (`Undervalued 3%`), with the note "share of covered stocks".

### Links

| Kind | Style | Example |
|---|---|---|
| Call to action | `--link`, no underline, text colour on hover, ends with "→" | Full analysis →, Methodology →, Terms → |

Every link uses `--link` (its own value in dark and light mode) and ends with "→". Back links start with "←". (Until 11 Oct 2026 the provenance line's Methodology link was a grey "quiet link"; changed so links look the same everywhere.)

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
- Value: 22–28px, `font-weight: 500`, monospace, `--text` or semantic colour

### Data rows

Used in stock detail views for model outputs (Graham Number, P/E fair value, EPV, DDM, …) and for key/value lists such as the About page's build details.

- Label left-aligned, 13px, muted
- Value 13–14px monospace, coloured by semantic meaning; right-aligned in tables, left-aligned in key/value lists
- Divider: `0.5px` border between rows

### Fair-value ladder

- The bar fills from zero to the current price; a dashed tick marks the model fair value.
- Fill colours: `--up-txt` when the price is below fair value, `--axis` (neutral) within ±3%, `--amber-fill` above it. Three clearly different hues, each at least 3:1 against the track. Two greens side by side can't be told apart.
- Legend on the table card's title row: "Below / Near / Above model fair value · Model fair value", 11.5px muted.

### Charts

- **Categorical palette** (sectors, countries, holdings), always in this order, cycling after the last:

  | # | Hex | | # | Hex |
  |---|---|---|---|---|
  | 1 | `#1DD6A4` Mint Pulse | | 7 | `#4A6B8A` Navy blue |
  | 2 | `#1A8C6E` Signal Teal | | 8 | `#6B9E8A` Muted teal-green |
  | 3 | `#5B8FA8` Steel blue | | 9 | `#2D6B7A` Deep teal |
  | 4 | `#2BA5A5` Mid teal | | 10 | `#A0B8B0` Silver teal |
  | 5 | `#3D7AB5` Slate blue | | 11 | `#7A9EBF` Powder blue |
  | 6 | `#8BA888` Sage green | | 12 | `#5E8C7A` Forest teal |

  (`_DONUT_PALETTE` in `uvalu/ui.py`.) It is all cool and calm on purpose. Red and amber never appear in a categorical palette because they mean danger and caution.
- **Semantic charts** (risk gauge, gains/losses, fair-value ladder) use the semantic colours instead: low risk `--up-txt`/Mint, moderate and elevated `--amber-fill`, high and critical `--down-txt`.
- Colour is never the only carrier: every slice or series also has a legend label with its value. Donut slices are separated by a 2px border in the panel colour.
- Gridlines `--grid`, axes and tick labels `--axis`, numbers monospace. Hover labels follow Tooltips.
- More than 12 categories: show the top 11 and group the rest as "Other".

### Disclosures

These texts are required and keep their wording; translations must keep their meaning.

| Element | Where | Wording / style |
|---|---|---|
| Beta banner | Top of every screen | "Free beta: a test version. Features and data can change, and the beta can end at any time." `--soft` background, 0.5px `--line` border, 8px radius, 11.5px muted text; the "Beta" label in `--up-txt`, weight 600 |
| Footer disclaimer | Bottom of every screen | "Uvalu is an analysis tool. Scores, fair values and signals are model outputs based on public data and are the same for every user. They are not personal investment advice…" + producer + links to the legal pages |
| Founder notice | Stock drawer and Analysis, when the founder holds the stock | "Disclosure: the founder of Uvalu holds a position in this stock. Its signal is calculated exactly like every other stock's." 12px muted |
| Badge tooltip | Every signal badge | See Signal badges |

---

## 9. Brand voice

### Principles

**Precise** — Every claim is grounded in a number. Uvalu does not use market sentiment language ("the market feels uncertain"). It uses data: "P/E of 9.4× against a model fair P/E of 14.2×."

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
| Risk | "Model outputs can be wrong. Share prices can stay below or above fair value for years." | "Beat the market with Uvalu." |

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
- Translations keep the voice: no buy-voice, no hype and no exclamation marks in any language. The disclosures keep their meaning (§8).

### Numbers and dates

Every number and date goes through the formatters in `uvalu/i18n.py` (`fmt_num`, `fmt_money`, `fmt_pct`, `fmt_compact`, `fmt_date`, `fmt_time`, `fmt_datetime`). They follow the user's region (CLDR), so `€42.80` in en-GB is `€ 42,80` in nl-BE and `42,80 €` in de-DE. Never format a number by hand.

| Rule | Example (en-GB) |
|---|---|
| Decimals: prices and amounts 2, percentages 1, multiples 1, scores 0 | `€42.80` · `34.2%` · `11.4×` · `82/100` |
| A `+` sign only on changes (P&L, deltas, returns), never on levels | `+€126.60` · `-3.1%` |
| The minus sign is the region's own, in front of the currency symbol | `-€86.01`, not `€-86.01` |
| No negative zero | `0.0%`, not `-0.0%` |
| Compact notation only where space is tight (tiles, chart labels) | `1.2B` / `1,2 Mrd.` |
| A converted amount carries `≈` | `≈ €1,240` |
| A missing value is an em dash, never 0 or "n/a" | `—` |
| Dates in the user's chosen style; chart ticks and compact labels use skeletons (`MMMd`, `yMMM`) | `7 Oct 2026` · `Oct 7` |
| Times in the user's time zone, the region's clock | `21:15` |

---

## 10. App icon

### Specifications

| Use | Size | Format | File in `assets/logo/` |
|---|---|---|---|
| Browser tab (app) | 32×32px | PNG | `uvalu-mark-small-32.png` (Streamlit `page_icon`) |
| Browser tab (web pages) | 16, 32, 48px | ICO | `favicon.ico` |
| Apple touch icon | 180×180px | PNG | `apple-touch-icon.png` |
| Web manifest | 192×192px, 512×512px | PNG | `icon-192.png`, `icon-512.png` |
| Mark without a tile | 512×512px | PNG | `uvalu-mark-512.png` |
| Social image | 1200×630px | PNG | `og-image.png` |

### Construction

- Tile: Deep Navy `#0D1F3C` (light variant: Surface `#F5F7FA`; monochrome: white), corner radius 22% of the tile (14px at 64px).
- Main mark at 75% of the tile; small mark at 84% (94% at 16px, where every pixel counts). Centred.
- Inks per the colour variants in §3; no text in the app icon.

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

**v1.4 — 11 Oct 2026**

- Logo: the Consensus mark (two rings for independent valuation models, a filled lens where they agree) replaces the V-stroke mark. Two weights (main above 32px, small at 32px and below), lockup rules, colour variants, usage by size and don'ts from `docs/design/logo-consensus-spec.md`.
- Wordmark: outlined Inter 500 everywhere, the app included (decided 11 Oct 2026); the v1.3 follow-up "outlined wordmark SVG" is done.
- The app's top bar follows the theme (light lockup in the light theme, decided 11 Oct 2026); Admin portal and sign-in stay dark. New token `--logo-ring`.
- App icon: files and sizes from `assets/logo/` (generated by `tools/build_logo.py`); tab icon is the small mark.

**v1.3 — 9 Oct 2026**

- Contrast: new `--link` token (`#167A60` light, `#3FBF98` dark) for link text, because Signal Teal is 4.2:1 on white. Mint Pulse is never text on light backgrounds. A 3:1 rule for meaningful graphics. Fair-value ladder fills are now up / neutral / amber instead of mint / teal / amber.
- Consistency fixes: badge size out of the Label row; page title 24px; 4px rule applies to layout spacing; 2px border covers focus and selected states; one radius rule for logo and app icon; `⚠` replaced by the `warning` symbol; the beta banner's tint (`--soft`) named and allowed; Mint Pulse no longer listed for badges; the Risk Don't example no longer echoes the tagline; P/E voice example uses "model fair P/E".
- Synced with `uvalu/styles.py`: full token table (`--up-bg`/`--down-bg`/`--amber-bg`, `--soft`, `--tile`, `--line-2`, `--uv-track`, `--grid`, `--axis`, `--shadow`), card shadow documented, radius set limited to 4/6/8/12px, No signal and No data badges specified.
- Added: chart palette, numbers and dates, other languages, focus ring, elevation, loading states, wordmark as outlined artwork, interim phone-layout rules.
- Code follow-ups (the app doesn't match v1.3 yet): add `--link` and use it for teal text links; ladder fills; `⚠` → `warning` in `_stale_chip_html`; beta "Beta" label `--mint` → `--up-txt`; round 7/9/10px radii; `:focus-visible` ring; outlined wordmark SVG.

**v1.2 — 7 Oct 2026**

- Uppercase small labels confirmed as the rule for 10–11px column headers, filter and metric labels (no longer "under review").
- Icons: Material Symbols (outlined) everywhere, marketing included; Tabler dropped.
- Tagline kept; usage guidance restored, with the rule never to place it next to a specific stock, signal or number.

**v1.1 — 7 Oct 2026** (matches app v2026.10.2)

- Signal badges renamed to the legal wording (Undervalued / Neutral / Low score / Fails quality screen / No signal), sentence case; "hard veto" → "quality screen"; voice principles and examples no longer present signals as buy instructions; tagline flagged for legal review (decided in v1.2).
- Added: dark-theme tokens, caution fill `#C98A3A`, signal provenance line, links, tooltips, fair-value ladder, disclosures, supporting-page layout.
- Typography: long-form body 14px, 17px section headings, 12px captions; the uppercase small-label exception made explicit.
- Fixed: wordmark-vs-name rule, "we" in legal texts, logo ring colour, icon set (Material Symbols), no DCF in the model list.

*Document version 1.4 — Uvalu Brand Guidelines*
