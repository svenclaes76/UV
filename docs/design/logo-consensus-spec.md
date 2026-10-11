# Uvalu logo: Consensus mark specification

Oct 11, 2026 · @Sven Claes

## Decision

Uvalu adopts the **Consensus** mark: two overlapping rings with a filled lens where they meet. It replaces the current V-stroke-and-ring mark in the Uvalu design system. The wordmark stays as it is: lowercase "uvalu" in medium weight, with the final u accented.

The mark comes in two weights. The **main mark** is for anything larger than 32 px. The **small mark** has heavier rings and a wider lens, and covers 32 px and below. Both are drawn on the [logo concepts canvas](https://claude.ai/code/artifact/90f1911a-ddc3-4bb0-af74-f238300b8d54), on the "02 Consensus, refined" sheet.

## Meaning

Each ring is an independent valuation model, such as a Graham Number or a PE fair value. The lens is where the models agree, and that zone of agreement is where Uvalu finds value. The mark therefore shows Uvalu's method, not a general idea of value.

- **Rings, outlined:** the models are tools, kept open and visible, never black boxes.
- **Lens, filled with mint or teal:** the only filled shape. It is the result, the part that matters.
- **Symmetry and plain geometry:** precise, systematic and calm, with no arrows, charts or growth clichés.

The circle and ring also continue the shapes of the previous mark, so the change reads as an evolution of the brand.

## Geometry

Both marks sit on a 64 × 64 grid. The lens is drawn first, and the rings are stroked on top so they trim its edges cleanly.

| Property | Main mark | Small mark |
| --- | --- | --- |
| Use at | larger than 32 px | 32 px and below |
| Ring radius | 17 | 18 |
| Ring centres (x, y) | (22, 32) and (42, 32) | (24, 32) and (40, 32) |
| Centre distance | 20 | 16 |
| Ring stroke | 4.5 | 5.5 |
| Lens tips (x, y) | (32, 18.25) and (32, 45.75) | (32, 15.88) and (32, 48.12) |
| Visible lens width | about 9.5 | about 14.5 |

Main mark, dark variant:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <path d="M32 18.25 A17 17 0 0 1 32 45.75 A17 17 0 0 1 32 18.25 Z" fill="#1DD6A4"/>
  <circle cx="22" cy="32" r="17" fill="none" stroke="#FFFFFF" stroke-width="4.5"/>
  <circle cx="42" cy="32" r="17" fill="none" stroke="#FFFFFF" stroke-width="4.5"/>
</svg>
```

Small mark, dark variant:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <path d="M32 15.88 A18 18 0 0 1 32 48.12 A18 18 0 0 1 32 15.88 Z" fill="#1DD6A4"/>
  <circle cx="24" cy="32" r="18" fill="none" stroke="#FFFFFF" stroke-width="5.5"/>
  <circle cx="40" cy="32" r="18" fill="none" stroke="#FFFFFF" stroke-width="5.5"/>
</svg>
```

For the other variants, swap only the two colours (next section). The geometry never changes between variants.

## Colour variants

There are three variants, and each uses exactly two inks on its ground. Dark is the primary variant, matching the app's default theme.

| Variant | Ground | Rings | Lens | Wordmark | Final u |
| --- | --- | --- | --- | --- | --- |
| Dark (primary) | Deep Navy `#0D1F3C` | White `#FFFFFF` | Mint Pulse `#1DD6A4` | White `#FFFFFF` | Mint Pulse `#1DD6A4` |
| Light | White `#FFFFFF` or Surface `#F5F7FA` | Deep Navy `#0D1F3C` | Signal Teal `#1A8C6E` | Deep Navy `#0D1F3C` | Signal Teal `#1A8C6E` |
| Monochrome | White, or transparent | Black `#000000` | Black `#000000` | Black `#000000` | Black `#000000` |

Mint is never used for the lens on a light ground, because it falls below 2:1 contrast there. In monochrome the lens stays visible as the only filled shape. For one-colour reversed use (white on a photo or dark print), make every ink white.

## Wordmark and lockup

The horizontal lockup is mark plus wordmark, with every dimension derived from the mark height H.

| Element | Spec | At H = 64 px |
| --- | --- | --- |
| Wordmark text | "uvalu", always lowercase | — |
| Typeface | Inter, weight 500 | — |
| Letter spacing | −0.03 em | −1.68 px |
| Font size | 0.875 × H | 56 px |
| Gap, mark to wordmark | 0.1875 × H | 12 px |
| Vertical alignment | x-height centred on the mark's centre line | baseline at about 47 px from the top |
| Accent | the final u only, in mint (dark) or teal (light) | — |
| Clear space | the height of the lowercase u on all sides | about 31 px |

In the delivered SVG files, convert the wordmark to outlines. The logo then renders identically everywhere, without depending on Inter being installed. Your design system's sans stack is the system font (with Roboto as fallback), so live text would not reliably render as Inter.

The mark can also stand alone (icon only). Use the lockup wherever there is room for it.

## Usage rules

Rule of thumb: rendered at 32 px or smaller, use the small mark; larger than that, use the main mark.

| Context | Mark | Variant | Rendered size | Mark inside tile |
| --- | --- | --- | --- | --- |
| Browser favicon | Small | Dark tile | 16 and 32 px | 94% (16 px), 84% (32 px) |
| Sidebar or header logo | Main, in lockup | Dark or light, by theme | mark height 24–32 px | no tile |
| Sign-in and onboarding | Main, in lockup | Dark | mark height 48–64 px | no tile |
| App and PWA icons | Main | Dark tile | 180, 192 and 512 px | 75% |
| Social and Open Graph image | Main, in lockup | Dark | mark height about 120 px on 1200 × 630 | no tile |
| Print, embossing, one-colour | Main or small, by size | Monochrome | — | — |

Icon tiles have a corner radius of 22% of the tile size, which is 14 px at 64 px. The minimum size is 16 px for the mark alone and a 24 px mark height for the lockup.

Don't:

- Recolour the rings and lens separately, add gradients or shadows, or outline the lens.
- Change the overlap, stroke weights or proportions, or mix main-mark rings with the small-mark lens.
- Use mint on a light ground, or put the dark variant straight onto white.
- Stretch, rotate or skew the mark, or move the accent away from the final u.

## Assets to export

Keep the existing file names, so the design system and the app pick up the new mark without code changes. The two `-small` files are new.

| File | Contents | Format |
| --- | --- | --- |
| `Logos/uvalu-mark.svg` | Main mark, dark, on a navy tile | SVG |
| `Logos/uvalu-mark-light.svg` | Main mark, light, on a Surface `#F5F7FA` tile | SVG |
| `Logos/uvalu-mark-mono.svg` | Main mark, monochrome, on a white tile | SVG |
| `Logos/uvalu-mark-small.svg` | Small mark, dark, on a navy tile | SVG |
| `Logos/uvalu-mark-small-mono.svg` | Small mark, monochrome | SVG |
| `Logos/uvalu-lockup-dark.svg` | Main mark plus outlined wordmark, transparent ground | SVG |
| `Logos/uvalu-lockup-light.svg` | Same, light colours | SVG |
| `Logos/uvalu-lockup-mono.svg` | Same, monochrome | SVG |
| `favicon.ico` | Small mark at 16, 32 and 48 px; also export the 32 px size as uvalu-mark-small-32.png | ICO |
| `apple-touch-icon.png` | Main mark tile, 180 × 180 | PNG |
| `icon-192.png`, `icon-512.png` | Main mark tile, for the PWA manifest | PNG |
| `uvalu-mark-512.png` | Main mark, transparent ground, 512 × 512 | PNG |
| `og-image.png` | Dark lockup on navy, 1200 × 630 | PNG |

## Implementation in the app

The app is built on Streamlit, so most of the change is two calls plus the new files.

1. Put the exported files in the app's static assets folder.
2. Set the browser tab icon to the small mark. `page_icon` needs a raster image, so use the 32 px PNG rather than the SVG:

   ```python
   st.set_page_config(page_title="Uvalu", page_icon="Logos/uvalu-mark-small-32.png")
   ```
3. Put the lockup in the sidebar, with the small mark as the collapsed-sidebar icon:

   ```python
   st.logo("Logos/uvalu-lockup-dark.svg", icon_image="Logos/uvalu-mark-small.svg")
   ```

   `st.logo` needs Streamlit 1.35 or later. If the app also offers the light theme, choose the dark or light lockup file from the active theme.
4. On the sign-in screen, use the dark lockup at a mark height of 48–64 px on the navy brand panel.
5. For any HTML outside Streamlit (a landing page or docs site), add these tags to `<head>`:

   ```html
   <link rel="icon" href="/favicon.ico" sizes="48x48">
   <link rel="icon" href="/Logos/uvalu-mark-small.svg" type="image/svg+xml">
   <link rel="apple-touch-icon" href="/apple-touch-icon.png">
   <meta property="og:image" content="/og-image.png">
   ```
6. Search the codebase for the old mark (its file names, and any inline SVG of the V-stroke) and replace every hit.
7. Check it: the favicon in both browser themes, the sidebar in light and dark, and the sign-in screen.

Keep the old mark files in version control until every surface has been checked.

## Design system update

Yes, update the Uvalu design system before the app. Everything built from it reads its Logo section and logo files, so the system is the single source of truth.

- [ ] Rewrite the README's Logo section: the Consensus mark, its meaning in one line, and the two weights.
- [ ] Replace the three variant descriptions (navy ground with white V-stroke, and so on) with the colour table above.
- [ ] Add the rule "small mark at 32 px and below", plus the sizes table from Usage rules.
- [ ] Replace `uvalu-mark.svg`, `uvalu-mark-light.svg` and `uvalu-mark-mono.svg`, and add the two `-small` files and the three lockups.
- [ ] Keep the rule "never redraw or recolour a mark by hand", now pointing to the new files.
- [ ] Add a note to the `wordmark` type style that logo files use the outlined wordmark, not live text.
- [ ] Raise the version in `tokens.json` from 1 to 2, so it is clear which logo a design was built with.

## Open decisions

- [x] **Wordmark typeface:** outline Inter 500 into the logo files. *Decided 11 Oct 2026 (Sven Claes).* Done in `assets/logo/` by `tools/build_logo.py`.
- [x] **Light theme in the app:** the top-bar lockup switches to the light variant in the light theme (dark variant in the dark theme). *Decided 11 Oct 2026 (Sven Claes).* The Admin portal and the sign-in panel are dark only and keep the dark lockup.
- [x] **Final exports:** the SVG, PNG and ICO files are produced (`assets/logo/`, 11 Oct 2026), and the favicon was checked on a real browser tab in light and dark browser themes (11 Oct 2026, Sven Claes): the navy tile reads on both.
