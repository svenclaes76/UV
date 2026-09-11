"""
Valuation & Risk Accuracy Audit — see docs/valuation_audit_plan.md.

Runs screener.compute_scores over the full cached fundamentals universe,
applies the documented check catalog (doc §2.2), aggregates findings per
ticker (not per check, doc §2.1), tiers them by severity (doc §2.3), and
writes a markdown report (doc §3.2). Diffs against a persisted
suppression/history log (doc §2.5) so a finding only resurfaces when its
disposition changes.

Detection only — no automatic fixes (doc §3.4). A finding's disposition
(fixed / documented-gap / dismissed-false-positive) is set by a human
reviewing the report, via --dispose, never by this tool on its own.

Usage:
    .venv/Scripts/python.exe -m tools.valuation_audit
    .venv/Scripts/python.exe -m tools.valuation_audit --dispose TICKER CHECK DISPOSITION "reason"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import screener

try:
    import settings as _settings
except Exception:                                       # pragma: no cover
    _settings = None

CATALOG_VERSION = "v1.4"

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"
FUNDAMENTALS_CACHE = CACHE_DIR / "fundamentals.json"
AUDIT_LOG_PATH = CACHE_DIR / "valuation_audit_log.json"
REPORT_PATH = CACHE_DIR / "valuation_audit_report.md"

# ── Check families (doc §2.2) ────────────────────────────────────────────────
BASIS_INTEGRITY = "basis_integrity"
SIGNAL_SAFETY = "signal_safety"
DISPLAY_CORRECTNESS = "display_correctness"

# ── Calibrated thresholds (doc §2.2) ─────────────────────────────────────────
NET_INCOME_RATIO_HIGH = 20.0
NET_INCOME_RATIO_LOW = 0.05
FV_RATIO_INFO = 20.0
FV_RATIO_NOTABLE = 50.0
FV_RATIO_CRITICAL = 200.0
DIVIDEND_YIELD_HIGH = 0.40
DIVIDEND_YIELD_LOW = -0.05

# Regression sentinels (doc §2.6) — tickers with a *shipped fix* to protect.
# BC.MI / LISPE.SW / INPHI.AS are documented, accepted gaps, not fixes — they
# have no "expected safe" state to assert, so they aren't sentinels; they
# surface through the regular check catalog and the suppression log instead.
SENTINELS = ["NAITR.AS", "SNBN.SW"]


def _sentinel_naitr(row: pd.Series) -> str | None:
    """NAITR.AS: confirmed-zero-volume hard veto must hold (Avoid)."""
    if bool(row.get("veto")) and str(row.get("Decision")) == "Avoid":
        return None
    return f"expected veto=True, Decision='Avoid'; got veto={row.get('veto')!r}, Decision={row.get('Decision')!r}"


def _sentinel_snb(row: pd.Series) -> str | None:
    """SNBN.SW: PTB_SANITY_FLOOR must hold fair_value dark (no Strong Buy)."""
    fv = row.get("fair_value")
    if (fv is None or (isinstance(fv, float) and pd.isna(fv))) and str(row.get("Decision")) != "Strong Buy":
        return None
    return f"expected fair_value NaN and Decision != 'Strong Buy'; got fair_value={fv!r}, Decision={row.get('Decision')!r}"


SENTINEL_ASSERTIONS = {
    "NAITR.AS": _sentinel_naitr,
    "SNBN.SW": _sentinel_snb,
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _first_finite(hist) -> float | None:
    """First finite value of a newest-first history list column, else None."""
    if not isinstance(hist, list):
        return None
    for v in hist:
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ── Check functions — each returns a bool Series aligned to df.index ────────
# (fair-value/price ratio is the one exception: it returns a tier Series,
# handled separately — see run_all_checks.)

def _num(df: pd.DataFrame, name: str) -> pd.Series:
    """Numeric column, index-aligned, all-NaN if the column is absent
    entirely — ``df.get(name)`` alone returns a bare ``None`` (not a Series)
    for a missing column, which breaks every ``pd.to_numeric``/``.notna()``
    call downstream."""
    if name not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return pd.to_numeric(df[name], errors="coerce")


def _obj(df: pd.DataFrame, name: str) -> pd.Series:
    """Object column, index-aligned, all-None if the column is absent."""
    if name not in df.columns:
        return pd.Series(None, index=df.index, dtype=object)
    return df[name]


def check_implied_ptb_floor(df: pd.DataFrame) -> pd.Series:
    """Re-asserts screener.PTB_SANITY_FLOOR. Doc §2.2 basis-integrity."""
    price = _num(df, "Price")
    bv = _num(df, "bookValue")
    ratio = price / bv
    return (bv > 0) & (price > 0) & (ratio < screener.PTB_SANITY_FLOOR)


NET_INCOME_MIN_ABS_EPS = 0.10   # coverage floor — see check_net_income_cross_validation


def check_net_income_cross_validation(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """trailingEps x sharesOutstanding vs. netIncomeHistory[0]. Doc §2.2.
    Returns (hits, coverage) — coverage is False where the check couldn't run
    (missing sharesOutstanding or netIncomeHistory), per the coverage-
    completeness meta-check (doc §2.2 catalog-integrity family).

    Two coverage exclusions found during implementation, not in the original
    doc calibration — both are precision floors, not threshold tuning:
    `sharesOutstanding == 0` and `|trailingEps| < NET_INCOME_MIN_ABS_EPS` both
    collapse `implied_ni` toward 0 mechanically regardless of whether the real
    EPS is right or wrong, so the ratio test carries no signal there. Run
    against the real universe: without these, 129 of 235 hits were pure
    near-zero-EPS/shares==0 noise (the same `sharesOutstanding == 0` rows the
    dedicated shares check already flags, double-counted here). With them,
    142 hits remain and every known case still classifies correctly — `BC.MI`
    /`MLVST.PA`/`ALHGO.PA`/`VEZ.DE` still fire, `ALNRG.PA`/`TPG0.DE`/`ALOPM.PA`
    /`ALWEC.PA`/`NWL.MI`/`ALGTR.PA` still clear."""
    eps = _num(df, "trailingEps")
    shares = _num(df, "sharesOutstanding")
    last_ni = _obj(df, "netIncomeHistory").map(_first_finite)
    last_ni = pd.to_numeric(last_ni, errors="coerce")

    coverage = (eps.notna() & (eps.abs() >= NET_INCOME_MIN_ABS_EPS)
               & shares.notna() & (shares != 0)
               & last_ni.notna() & (last_ni != 0))
    implied_ni = eps * shares
    ratio = implied_ni / last_ni
    sign_mismatch = ((implied_ni > 0) & (last_ni < 0)) | ((implied_ni < 0) & (last_ni > 0))
    hits = coverage & (sign_mismatch | (ratio > NET_INCOME_RATIO_HIGH) | (ratio < NET_INCOME_RATIO_LOW))
    return hits, coverage


def check_shares_outstanding_sanity(df: pd.DataFrame) -> pd.Series:
    """Confirmed-zero sharesOutstanding — exact, not a fuzzy low band (a fuzzy
    band would misfire on SNBN.SW's genuine 100,000). Doc §2.2."""
    shares = _num(df, "sharesOutstanding")
    return shares.notna() & (shares == 0)


def check_zero_volume_vs_strong_buy(df: pd.DataFrame) -> pd.Series:
    """Regression sentinel in check form — should never fire post-fix. Doc §2.2."""
    vol = _num(df, "averageVolume")
    return (vol == 0) & (_obj(df, "Decision") == "Strong Buy")


def check_fv_basis_thin_vs_strong_buy(df: pd.DataFrame) -> pd.Series:
    """Regression sentinel in check form — should never fire post-fix. Doc §2.2."""
    thin = _obj(df, "fv_basis_thin").fillna(False).astype(bool)
    return thin & (_obj(df, "Decision") == "Strong Buy")


def check_decision_veto_consistency(df: pd.DataFrame) -> pd.Series:
    """veto == True must imply Decision == 'Avoid'. Pure code invariant,
    no ticker-specific false-positive risk. Doc §2.2."""
    veto = _obj(df, "veto").fillna(False).astype(bool)
    return veto & (_obj(df, "Decision") != "Avoid")


def check_fair_value_price_ratio(df: pd.DataFrame) -> pd.Series:
    """Fair-value/price ratio outlier tier (NaN / informational / notable /
    critical) — magnitude alone, NOT final severity (doc §2.2/§2.3: needs a
    basis-integrity hit on the same ticker to escalate past informational)."""
    price = _num(df, "Price")
    fv = _num(df, "fair_value")
    ratio = (fv / price).where((price > 0) & (fv > 0))
    tier = pd.Series(float("nan"), index=df.index, dtype=object)
    tier[ratio > FV_RATIO_INFO] = "informational"
    tier[ratio > FV_RATIO_NOTABLE] = "notable"
    tier[ratio > FV_RATIO_CRITICAL] = "critical"
    return tier


def check_dividend_yield_sanity(df: pd.DataFrame) -> pd.Series:
    """Symptom check — almost always co-fires with a basis-integrity or
    zero-volume hit on the same row (doc §2.2). The < -5% branch is
    defensive/untested: dividendYield has no code path that goes negative
    today."""
    dy = _num(df, "dividendYield")
    return dy.notna() & ((dy > DIVIDEND_YIELD_HIGH) | (dy < DIVIDEND_YIELD_LOW))


@dataclass(frozen=True)
class Check:
    name: str
    family: str
    status: str          # "shipped" | "calibrated"
    doc_ref: str
    description: str


CHECK_REGISTRY: list[Check] = [
    Check("implied_ptb_floor", BASIS_INTEGRITY, "shipped", "§2.2",
          "Price/bookValue below PTB_SANITY_FLOOR — re-asserts the shipped guard."),
    Check("net_income_cross_validation", BASIS_INTEGRITY, "calibrated", "§2.2",
          "trailingEps x sharesOutstanding inconsistent with netIncomeHistory[0]."),
    Check("shares_outstanding_sanity", BASIS_INTEGRITY, "calibrated", "§2.2",
          "sharesOutstanding is exactly 0."),
    Check("zero_volume_vs_strong_buy", SIGNAL_SAFETY, "shipped", "§2.2",
          "Confirmed zero averageVolume co-occurring with Decision == 'Strong Buy'."),
    Check("fv_basis_thin_vs_strong_buy", SIGNAL_SAFETY, "shipped", "§2.2",
          "fv_basis_thin co-occurring with Decision == 'Strong Buy'."),
    Check("decision_veto_consistency", SIGNAL_SAFETY, "calibrated", "§2.2",
          "veto == True without Decision == 'Avoid'."),
    Check("fair_value_price_ratio", DISPLAY_CORRECTNESS, "calibrated", "§2.2",
          "fair_value many multiples of Price (bands: >20x/>50x/>200x)."),
    Check("dividend_yield_sanity", DISPLAY_CORRECTNESS, "calibrated", "§2.2",
          "dividendYield > 40% or < -5% (symptom check)."),
]

_CHECK_BY_NAME = {c.name: c for c in CHECK_REGISTRY}


@dataclass
class CheckOutcome:
    hits: dict[str, pd.Series] = field(default_factory=dict)
    tiers: dict[str, pd.Series] = field(default_factory=dict)   # for magnitude-tiered checks
    coverage: dict[str, pd.Series] = field(default_factory=dict)  # only for coverage-limited checks


def run_all_checks(df: pd.DataFrame) -> CheckOutcome:
    out = CheckOutcome()
    out.hits["implied_ptb_floor"] = check_implied_ptb_floor(df)

    ni_hits, ni_coverage = check_net_income_cross_validation(df)
    out.hits["net_income_cross_validation"] = ni_hits
    out.coverage["net_income_cross_validation"] = ni_coverage

    out.hits["shares_outstanding_sanity"] = check_shares_outstanding_sanity(df)
    out.hits["zero_volume_vs_strong_buy"] = check_zero_volume_vs_strong_buy(df)
    out.hits["fv_basis_thin_vs_strong_buy"] = check_fv_basis_thin_vs_strong_buy(df)
    out.hits["decision_veto_consistency"] = check_decision_veto_consistency(df)

    fv_tier = check_fair_value_price_ratio(df)
    out.tiers["fair_value_price_ratio"] = fv_tier
    out.hits["fair_value_price_ratio"] = fv_tier.notna()

    out.hits["dividend_yield_sanity"] = check_dividend_yield_sanity(df)
    return out


# ── Aggregation (doc §2.1 step 4) ────────────────────────────────────────────

@dataclass
class Finding:
    ticker: str
    decision: str
    veto: bool
    severity: str                 # critical | notable | informational
    checks_failed: list[str]
    details: dict[str, str]       # check_name -> human-readable detail


def _severity_for(checks_failed: list[str], decision: str) -> str:
    families = {_CHECK_BY_NAME[c].family for c in checks_failed}
    if SIGNAL_SAFETY in families:
        return "critical"
    if BASIS_INTEGRITY in families:
        return "critical" if decision == "Strong Buy" else "notable"
    return "informational"


def _detail_for(check_name: str, row: pd.Series, outcome: CheckOutcome) -> str:
    if check_name == "implied_ptb_floor":
        price = row.get("Price"); bv = row.get("bookValue")
        ratio = (price / bv) if bv else None
        return f"Price/bookValue = {ratio:.4f} (< {screener.PTB_SANITY_FLOOR})" if ratio is not None else "implied P/B"
    if check_name == "net_income_cross_validation":
        eps = row.get("trailingEps"); shares = row.get("sharesOutstanding")
        last_ni = _first_finite(row.get("netIncomeHistory"))
        implied = (eps or 0) * (shares or 0)
        return f"implied NI {implied:,.0f} vs. reported {last_ni:,.0f}" if last_ni else "net-income mismatch"
    if check_name == "shares_outstanding_sanity":
        return "sharesOutstanding == 0"
    if check_name == "zero_volume_vs_strong_buy":
        return "averageVolume == 0 and Decision == 'Strong Buy'"
    if check_name == "fv_basis_thin_vs_strong_buy":
        return "fv_basis_thin and Decision == 'Strong Buy'"
    if check_name == "decision_veto_consistency":
        return f"veto == True but Decision == {row.get('Decision')!r}"
    if check_name == "fair_value_price_ratio":
        price = row.get("Price"); fv = row.get("fair_value")
        ratio = (fv / price) if price else None
        tier = outcome.tiers["fair_value_price_ratio"].get(row.name)
        return f"fair_value/Price = {ratio:.1f}x ({tier})" if ratio is not None else "fair value/price ratio"
    if check_name == "dividend_yield_sanity":
        dy = row.get("dividendYield")
        return f"dividendYield = {dy * 100:.1f}%" if dy is not None else "dividend yield"
    return check_name


def aggregate_findings(df: pd.DataFrame, outcome: CheckOutcome) -> list[Finding]:
    any_hit = pd.Series(False, index=df.index)
    for s in outcome.hits.values():
        any_hit = any_hit | s.fillna(False)

    findings: list[Finding] = []
    for idx in df.index[any_hit]:
        row = df.loc[idx]
        checks_failed = [name for name, hits in outcome.hits.items() if bool(hits.get(idx, False))]
        decision = str(row.get("Decision"))
        severity = _severity_for(checks_failed, decision)
        details = {name: _detail_for(name, row, outcome) for name in checks_failed}
        findings.append(Finding(
            ticker=str(row.get("Ticker", idx)),
            decision=decision,
            veto=bool(row.get("veto")),
            severity=severity,
            checks_failed=checks_failed,
            details=details,
        ))
    order = {"critical": 0, "notable": 1, "informational": 2}
    findings.sort(key=lambda f: (order[f.severity], f.ticker))
    return findings


# ── Self-explanation surfacing (doc §2.4) ────────────────────────────────────

def _explanation_for(row: pd.Series) -> list[str]:
    lines = []
    reasons = row.get("fv_dark_reasons")
    if isinstance(reasons, dict) and reasons:
        lines.append("fv_dark_reasons: " + ", ".join(f"{k}={v}" for k, v in reasons.items()))
    try:
        lines.append("decision_reason: " + screener.decision_reason(row))
    except Exception:
        pass
    if bool(row.get("veto")):
        try:
            from uvalu.components import veto_reason_str
            lines.append("veto_reason: " + veto_reason_str(row))
        except Exception:
            pass
    return lines


# ── Suppression / history log (doc §2.5) ─────────────────────────────────────

def load_log(path: Path = AUDIT_LOG_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_log(log: dict, path: Path = AUDIT_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, sort_keys=True), encoding="utf-8")


def _log_key(ticker: str, check_name: str) -> str:
    return f"{ticker}::{check_name}"


def diff_against_log(findings: list[Finding], log: dict, *, commit: str, now: str) -> tuple[list[Finding], dict, list[str]]:
    """Returns (findings_to_show, updated_log, regressions).

    A ticker+check pair is suppressed from the headline report only when its
    logged disposition is 'documented-gap' or 'dismissed-false-positive' and
    it's still failing the *same* check it was dispositioned for. A 'fixed'
    entry that fires again is a regression — always shown, never suppressed.
    A pair with no disposition yet (new, or previously seen but not yet
    triaged) always shows.
    """
    updated = dict(log)
    regressions: list[str] = []
    shown: list[Finding] = []

    for f in findings:
        visible_checks = []
        for check_name in f.checks_failed:
            key = _log_key(f.ticker, check_name)
            entry = updated.get(key)
            if entry is None:
                updated[key] = {
                    "first_seen": now, "commit": commit, "catalog_version": CATALOG_VERSION,
                    "disposition": None, "reason": None, "last_confirmed": now,
                }
                visible_checks.append(check_name)
                continue

            entry["last_confirmed"] = now
            disposition = entry.get("disposition")
            if disposition == "fixed":
                regressions.append(key)
                visible_checks.append(check_name)
            elif disposition in ("documented-gap", "dismissed-false-positive"):
                pass  # suppressed — still updates last_confirmed above
            else:
                visible_checks.append(check_name)  # pending triage

        if visible_checks:
            shown.append(Finding(
                ticker=f.ticker, decision=f.decision, veto=f.veto, severity=f.severity,
                checks_failed=visible_checks,
                details={k: v for k, v in f.details.items() if k in visible_checks},
            ))

    return shown, updated, regressions


def set_disposition(ticker: str, check_name: str, disposition: str, reason: str,
                     *, log_path: Path = AUDIT_LOG_PATH) -> None:
    if disposition not in ("fixed", "documented-gap", "dismissed-false-positive"):
        raise ValueError(f"unknown disposition: {disposition!r}")
    if check_name not in _CHECK_BY_NAME:
        raise ValueError(f"unknown check: {check_name!r}")
    log = load_log(log_path)
    key = _log_key(ticker, check_name)
    now = datetime.now(timezone.utc).isoformat()
    entry = log.get(key) or {
        "first_seen": now, "commit": _git_commit(), "catalog_version": CATALOG_VERSION,
    }
    entry["disposition"] = disposition
    entry["reason"] = reason
    entry["last_confirmed"] = now
    log[key] = entry
    save_log(log, log_path)


# ── Regression sentinels (doc §2.6) ──────────────────────────────────────────

def _is_placeholder_row(row: pd.Series) -> bool:
    """True for a row that's a bare placeholder stub screener._fetch_and_store
    writes while the real fetch is pending — {Name, Ticker, ISIN, fetched_at:
    ""} and nothing else. Confirmed live during this tool's own build: another
    running app instance's background fetcher left NAITR.AS in exactly this
    state across several consecutive audit runs — evaluating a sentinel
    against it asserts nothing about the real fix, just about fetch timing."""
    fetched_at = row.get("fetched_at")
    return fetched_at is None or (isinstance(fetched_at, float) and pd.isna(fetched_at)) or fetched_at == ""


def run_sentinels(df: pd.DataFrame) -> dict[str, str | None]:
    """{ticker: None (passed) | failure description} for every sentinel ticker
    present in the current cache with real (non-placeholder) data. A sentinel
    ticker absent from the cache, or present only as a pending-fetch
    placeholder, is silently skipped, not a failure — the fundamentals cache
    is a live, moving dataset that doesn't guarantee any specific ticker has
    settled, real data every run."""
    results: dict[str, str | None] = {}
    for ticker in SENTINELS:
        if ticker not in df.index:
            continue
        row = df.loc[ticker]
        if _is_placeholder_row(row):
            continue
        results[ticker] = SENTINEL_ASSERTIONS[ticker](row)
    return results


# ── Pipeline ──────────────────────────────────────────────────────────────

def load_scored_universe(cache_path: Path = FUNDAMENTALS_CACHE) -> pd.DataFrame:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    rows = []
    for ticker, rec in data.items():
        if not isinstance(rec, dict):
            continue
        row = dict(rec)
        row["Ticker"] = ticker
        rows.append(row)
    df = pd.DataFrame(rows)

    kwargs = {}
    if _settings is not None:
        try:
            max_de, max_payout, min_mos, buy_threshold = _settings.get_veto_thresholds()
            kwargs = dict(max_debt_equity=max_de, max_payout=max_payout,
                          min_mos=min_mos, buy_threshold=buy_threshold,
                          weights=_settings.get_score_weights())
        except Exception:
            kwargs = {}
    scored = screener.compute_scores(df, **kwargs)
    return scored.set_index("Ticker", drop=False)


def render_report(findings: list[Finding], scored: pd.DataFrame, outcome: CheckOutcome,
                   sentinel_results: dict[str, str | None], regressions: list[str],
                   *, commit: str, universe_size: int, info_cap: int = 10) -> str:
    lines = [
        "# Valuation & Risk Accuracy Audit",
        "",
        f"- Run: {datetime.now(timezone.utc).isoformat()}",
        f"- Universe: {universe_size} tickers",
        f"- `screener.py` commit: `{commit}`",
        f"- Catalog version: `{CATALOG_VERSION}`",
        "",
    ]

    if regressions:
        lines += ["## Regressions — previously fixed, failing again", ""]
        for key in regressions:
            lines.append(f"- `{key}` — was dispositioned `fixed`, now failing the same check again.")
        lines.append("")

    by_severity = {"critical": [], "notable": [], "informational": []}
    for f in findings:
        by_severity[f.severity].append(f)

    def _render_finding(f: Finding) -> list[str]:
        out = [f"### `{f.ticker}` — {f.decision}" + (" (vetoed)" if f.veto else "")]
        for check_name in f.checks_failed:
            out.append(f"- **{check_name}** ({_CHECK_BY_NAME[check_name].doc_ref}): {f.details[check_name]}")
        row = scored.loc[f.ticker] if f.ticker in scored.index else None
        if row is not None:
            for line in _explanation_for(row):
                out.append(f"  - {line}")
        out.append("")
        return out

    lines += ["## Critical", ""]
    if not by_severity["critical"]:
        lines.append("_None._\n")
    for f in by_severity["critical"]:
        lines += _render_finding(f)

    lines += ["## Notable", ""]
    if not by_severity["notable"]:
        lines.append("_None._\n")
    for f in by_severity["notable"]:
        lines += _render_finding(f)

    lines += ["## Informational", ""]
    info = by_severity["informational"]
    if not info:
        lines.append("_None._\n")
    else:
        for f in info[:info_cap]:
            lines += _render_finding(f)
        remaining = len(info) - info_cap
        if remaining > 0:
            lines.append(f"_+ {remaining} more informational hits — see `{AUDIT_LOG_PATH.name}` for the full list._\n")

    lines += ["## Check coverage", ""]
    for name, coverage in outcome.coverage.items():
        evaluated = int(coverage.sum())
        lines.append(f"- `{name}`: evaluated {evaluated}/{len(coverage)} rows "
                     f"({len(coverage) - evaluated} skipped — required fields missing)")
    if not outcome.coverage:
        lines.append("_All active checks have full coverage (no field-dependent skips)._")
    lines.append("")

    lines += ["## Regression sentinels", ""]
    if not sentinel_results:
        lines.append("_No sentinel tickers present in this run's cache._")
    for ticker, failure in sentinel_results.items():
        lines.append(f"- `{ticker}`: {'OK' if failure is None else 'FAILED — ' + failure}")
    if any(f is not None for f in sentinel_results.values()):
        lines.append("")
        lines.append("_A sentinel failure can be a real regression, or a transient read against a_ "
                     "_fundamentals cache mid-refetch by a running app instance (observed during_ "
                     "_this tool's own build — re-run before treating it as confirmed)._")
    lines.append("")

    return "\n".join(lines)


@dataclass
class AuditRun:
    report: str
    shown: list[Finding]
    regressions: list[str]
    sentinel_results: dict[str, str | None]
    report_path: Path


def run(cache_path: Path = FUNDAMENTALS_CACHE, log_path: Path = AUDIT_LOG_PATH,
        report_path: Path = REPORT_PATH) -> AuditRun:
    scored = load_scored_universe(cache_path)
    outcome = run_all_checks(scored)
    findings = aggregate_findings(scored, outcome)

    commit = _git_commit()
    now = datetime.now(timezone.utc).isoformat()
    log = load_log(log_path)
    shown, updated_log, regressions = diff_against_log(findings, log, commit=commit, now=now)
    save_log(updated_log, log_path)

    sentinel_results = run_sentinels(scored)

    report = render_report(shown, scored, outcome, sentinel_results, regressions,
                           commit=commit, universe_size=len(scored))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return AuditRun(report=report, shown=shown, regressions=regressions,
                    sentinel_results=sentinel_results, report_path=report_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dispose", nargs=4, metavar=("TICKER", "CHECK", "DISPOSITION", "REASON"),
                        help="Record a triage disposition instead of running the audit: "
                             "fixed | documented-gap | dismissed-false-positive")
    args = parser.parse_args(argv)

    if args.dispose:
        ticker, check_name, disposition, reason = args.dispose
        set_disposition(ticker, check_name, disposition, reason)
        print(f"Recorded {disposition!r} for {ticker}::{check_name}")
        return 0

    result = run()
    counts = {"critical": 0, "notable": 0, "informational": 0}
    for f in result.shown:
        counts[f.severity] += 1
    print(f"Critical: {counts['critical']}  Notable: {counts['notable']}  "
         f"Informational: {counts['informational']}")
    if result.regressions:
        print(f"REGRESSIONS: {', '.join(result.regressions)}")
    sentinel_fail = {t: r for t, r in result.sentinel_results.items() if r is not None}
    if sentinel_fail:
        print(f"SENTINEL FAILURES: {sentinel_fail}")
    print(f"Report written to {result.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
