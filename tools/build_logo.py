"""Generate every Uvalu logo file in ``assets/logo/`` from the Consensus spec.

Usage:
    python tools/build_logo.py            # write all SVG, PNG and ICO files
    python tools/build_logo.py --check    # exit 1 when an SVG differs from what the spec gives

Source of truth: ``docs/design/logo-consensus-spec.md`` (geometry, colour
variants, lockup, asset table). Nobody edits a file in ``assets/logo/`` by
hand: change a value here and run the script.

The wordmark is converted to outlines with fontTools from Inter Medium
(``tools/fonts/Inter-Medium.ttf``, Inter 4.1 from the official rsms/inter
release, SIL Open Font License in ``tools/fonts/Inter-OFL.txt``), so the logo
renders the same everywhere without Inter installed. Kerning comes from the
font's GPOS ``kern`` pairs, tracking is −0.03 em. Rasters (PNG, ICO) are drawn
by resvg. fontTools and resvg-py are dev-only dependencies (requirements.txt,
Dev/test section).
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"
FONT = ROOT / "tools" / "fonts" / "Inter-Medium.ttf"

# ── Spec values ───────────────────────────────────────────────────────────────
GRID = 64
MAIN = {"r": 17, "cx": (22, 42), "stroke": 4.5, "lens": "M32 18.25 A17 17 0 0 1 32 45.75 A17 17 0 0 1 32 18.25 Z"}
SMALL = {"r": 18, "cx": (24, 40), "stroke": 5.5, "lens": "M32 15.88 A18 18 0 0 1 32 48.12 A18 18 0 0 1 32 15.88 Z"}

NAVY, WHITE, SURFACE, BLACK = "#0D1F3C", "#FFFFFF", "#F5F7FA", "#000000"
MINT, TEAL = "#1DD6A4", "#1A8C6E"
# variant: (rings + wordmark, lens + final u)
INKS = {"dark": (WHITE, MINT), "light": (NAVY, TEAL), "mono": (BLACK, BLACK)}

TILE_RADIUS = 0.22          # of the tile size
MAIN_IN_TILE = 0.75
SMALL_IN_TILE = 0.84
SMALL_IN_TILE_16 = 0.94

WORDMARK = "uvalu"
FONT_SIZE = 56              # 0.875 × H
TRACKING_EM = -0.03         # −1.68 at 56
WORD_GAP = 12               # 0.1875 × H, from the mark's grid edge
BASELINE = 47               # x-height centred on the mark's centre line


def _num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ── Mark ──────────────────────────────────────────────────────────────────────

def mark_elements(geom: dict, rings: str, lens: str) -> str:
    """Lens first, then the two rings stroked on top (they trim its edges)."""
    sw = _num(geom["stroke"])
    circles = "".join(
        f'<circle cx="{cx}" cy="32" r="{geom["r"]}" fill="none" stroke="{rings}" stroke-width="{sw}"/>'
        for cx in geom["cx"])
    return f'<path d="{geom["lens"]}" fill="{lens}"/>{circles}'


def _svg(view_w: float, view_h: float, body: str, label: str = "uvalu") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_num(view_w)} {_num(view_h)}" '
            f'role="img" aria-label="{label}">{body}</svg>\n')


def tile_svg(geom: dict, variant: str, ground: "str | None", scale: float) -> str:
    """The mark on a rounded tile (or a transparent ground when ``ground`` is
    None), scaled to ``scale`` of the tile and centred."""
    rings, lens = INKS[variant]
    body = ""
    if ground:
        r = _num(round(GRID * TILE_RADIUS))      # 14 at 64 (spec)
        body += f'<rect width="{GRID}" height="{GRID}" rx="{r}" ry="{r}" fill="{ground}"/>'
    off = _num(GRID * (1 - scale) / 2)
    body += f'<g transform="translate({off} {off}) scale({_num(scale)})">{mark_elements(geom, rings, lens)}</g>'
    return _svg(GRID, GRID, body)


# ── Wordmark outlines ─────────────────────────────────────────────────────────

def _kern_pairs(font) -> dict:
    """(left glyph, right glyph) → x-advance adjustment in font units, from the
    GPOS ``kern`` feature (pair positioning, formats 1 and 2)."""
    pairs: dict = {}
    if "GPOS" not in font:
        return pairs
    gpos = font["GPOS"].table
    lookups = set()
    for rec in gpos.FeatureList.FeatureRecord:
        if rec.FeatureTag == "kern":
            lookups.update(rec.Feature.LookupListIndex)
    for li in sorted(lookups):
        lookup = gpos.LookupList.Lookup[li]
        subtables = lookup.SubTable
        if lookup.LookupType == 9:                       # extension
            subtables = [st.ExtSubTable for st in subtables]
        for st in subtables:
            if getattr(st, "LookupType", 2) != 2 and not hasattr(st, "PairSet") and not hasattr(st, "Class1Record"):
                continue
            cov = st.Coverage.glyphs
            if st.Format == 1:
                for first, pset in zip(cov, st.PairSet):
                    for pvr in pset.PairValueRecord:
                        v = getattr(pvr.Value1, "XAdvance", 0) or 0
                        pairs.setdefault((first, pvr.SecondGlyph), v)
            elif st.Format == 2:
                c1, c2 = st.ClassDef1.classDefs, st.ClassDef2.classDefs
                for first in cov:
                    row = st.Class1Record[c1.get(first, 0)]
                    for second in font.getGlyphOrder():
                        rec2 = row.Class2Record[c2.get(second, 0)]
                        v = getattr(rec2.Value1, "XAdvance", 0) or 0
                        if v:
                            pairs.setdefault((first, second), v)
    return pairs


def wordmark_paths(main_ink: str, accent: str, x0: float) -> "tuple[str, float]":
    """Outlined "uvalu" from ``x0`` on the baseline; returns (SVG paths, right
    edge of the last glyph's ink)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    upm = font["head"].unitsPerEm
    scale = FONT_SIZE / upm
    cmap, gs, hmtx = font.getBestCmap(), font.getGlyphSet(), font["hmtx"]
    names = [cmap[ord(c)] for c in WORDMARK]
    kern = _kern_pairs(font)
    tracking = TRACKING_EM * upm

    pen_x, parts, right = 0.0, [], x0
    for i, name in enumerate(names):
        svg_pen = SVGPathPen(gs, ntos=lambda v: _num(v))
        # Font units → SVG: scale, flip y, move to the baseline.
        gs[name].draw(TransformPen(svg_pen, (scale, 0, 0, -scale, x0 + pen_x * scale, BASELINE)))
        fill = accent if i == len(names) - 1 else main_ink
        parts.append(f'<path d="{svg_pen.getCommands()}" fill="{fill}"/>')
        glyf = font["glyf"][name] if "glyf" in font else None
        if glyf is not None and hasattr(glyf, "xMax"):
            right = max(right, x0 + (pen_x + glyf.xMax) * scale)
        pen_x += hmtx[name][0] + tracking
        if i + 1 < len(names):
            pen_x += kern.get((name, names[i + 1]), 0)
    return "".join(parts), right


def lockup_svg(variant: str) -> str:
    """Main mark plus outlined wordmark on a transparent ground. The viewBox
    keeps the mark's 64-unit grid as its height (so the rendered height is the
    mark height H) and ends at the wordmark's ink; no clear space."""
    rings, lens = INKS[variant]
    words, right = wordmark_paths(rings, lens, GRID + WORD_GAP)
    body = mark_elements(MAIN, rings, lens) + words
    return _svg(round(right + 0.005, 2), GRID, body)


# ── Asset table ───────────────────────────────────────────────────────────────

def svg_files() -> "dict[str, str]":
    return {
        "uvalu-mark.svg": tile_svg(MAIN, "dark", NAVY, MAIN_IN_TILE),
        "uvalu-mark-light.svg": tile_svg(MAIN, "light", SURFACE, MAIN_IN_TILE),
        "uvalu-mark-mono.svg": tile_svg(MAIN, "mono", WHITE, MAIN_IN_TILE),
        "uvalu-mark-small.svg": tile_svg(SMALL, "dark", NAVY, SMALL_IN_TILE),
        "uvalu-mark-small-mono.svg": tile_svg(SMALL, "mono", None, 1.0),
        "uvalu-lockup-dark.svg": lockup_svg("dark"),
        "uvalu-lockup-light.svg": lockup_svg("light"),
        "uvalu-lockup-mono.svg": lockup_svg("mono"),
    }


def _png(svg: str, width: int, height: int) -> bytes:
    import resvg_py
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height))


def raster_files(svgs: "dict[str, str]") -> "dict[str, bytes]":
    from PIL import Image

    small_tile = svgs["uvalu-mark-small.svg"]
    small_tile_16 = tile_svg(SMALL, "dark", NAVY, SMALL_IN_TILE_16)
    main_tile = svgs["uvalu-mark.svg"]

    frames = [Image.open(io.BytesIO(_png(small_tile_16 if px == 16 else small_tile, px, px))).convert("RGBA")
              for px in (16, 32, 48)]
    ico = io.BytesIO()
    frames[-1].save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[:-1])

    # Open Graph: dark lockup on navy, 1200 × 630, mark height 120, centred.
    lockup = svgs["uvalu-lockup-dark.svg"]
    lw = float(lockup.split('viewBox="0 0 ')[1].split(" ")[0])
    h = 120
    w = lw * h / GRID
    inner = lockup.split(">", 1)[1].rsplit("</svg>", 1)[0]
    og = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">'
          f'<rect width="1200" height="630" fill="{NAVY}"/>'
          f'<g transform="translate({_num((1200 - w) / 2)} {_num((630 - h) / 2)}) scale({_num(h / GRID)})">'
          f'{inner}</g></svg>')

    return {
        "favicon.ico": ico.getvalue(),
        "uvalu-mark-small-32.png": _png(small_tile, 32, 32),
        "apple-touch-icon.png": _png(main_tile, 180, 180),
        "icon-192.png": _png(main_tile, 192, 192),
        "icon-512.png": _png(main_tile, 512, 512),
        "uvalu-mark-512.png": _png(tile_svg(MAIN, "dark", None, 1.0), 512, 512),
        "og-image.png": _png(og, 1200, 630),
    }


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare the SVGs with the spec, write nothing")
    args = ap.parse_args(argv)

    svgs = svg_files()
    if args.check:
        stale = [n for n, s in svgs.items() if not (OUT / n).exists() or (OUT / n).read_text(encoding="utf-8") != s]
        for n in stale:
            print(f"stale: assets/logo/{n}")
        return 1 if stale else 0

    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in svgs.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    for name, data in raster_files(svgs).items():
        (OUT / name).write_bytes(data)
    print(f"wrote {len(svgs)} SVG and 7 raster files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
