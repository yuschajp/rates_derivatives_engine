"""
market_data.py
──────────────
Fetches live US rates from the FRED API (St. Louis Fed).
No API key required for most series.

Provides:
  - US Treasury par rates (1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y)
  - SOFR (Secured Overnight Financing Rate)
  - Effective Fed Funds Rate (EFFR)
  - Fed Funds Target Range

All data sourced from:
  https://fred.stlouisfed.org/
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, Optional

# ── FRED series IDs ───────────────────────────────────────────────────────────
FRED_SERIES = {
    # Treasury par yields (Constant Maturity)
    "1Y":  "DGS1",
    "2Y":  "DGS2",
    "3Y":  "DGS3",
    "5Y":  "DGS5",
    "7Y":  "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
    # Money market rates
    "SOFR":  "SOFR",
    "EFFR":  "FEDFUNDS",
    "3M":    "DGS3MO",
    "6M":    "DGS6MO",
}

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

# ── Fallback rates (as of mid-2026, for when FRED is unavailable) ─────────────
FALLBACK_RATES = {
    "3M":  4.32,
    "6M":  4.28,
    "1Y":  4.15,
    "2Y":  4.05,
    "3Y":  4.02,
    "5Y":  4.08,
    "7Y":  4.15,
    "10Y": 4.22,
    "20Y": 4.48,
    "30Y": 4.52,
    "SOFR": 4.30,
    "EFFR": 4.33,
}


def _fetch_fred_series(series_id: str) -> Optional[float]:
    """Fetch latest value for a FRED series. Returns rate in percent."""
    try:
        url = f"{FRED_BASE}{series_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "rates-engine/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            lines = resp.read().decode("utf-8").strip().split("\n")
            # CSV: DATE,VALUE — get last non-empty row
            for line in reversed(lines[1:]):
                parts = line.split(",")
                if len(parts) == 2 and parts[1].strip() not in (".", ""):
                    return float(parts[1].strip())
    except Exception:
        return None
    return None


def fetch_live_rates(use_fallback: bool = True) -> Dict:
    """
    Fetch current US market rates from FRED.
    Falls back to stored rates if FRED is unavailable.

    Returns dict with:
      - treasury_yields: {tenor: rate_in_decimal}
      - money_market: {name: rate_in_decimal}
      - source: "FRED" or "fallback"
      - fetched_at: ISO timestamp
    """
    print("Fetching live rates from FRED...")
    rates = {}
    source = "FRED"

    for label, series_id in FRED_SERIES.items():
        val = _fetch_fred_series(series_id)
        if val is not None:
            rates[label] = val / 100  # convert percent to decimal
        elif use_fallback:
            rates[label] = FALLBACK_RATES.get(label, 0.04)
            source = "fallback"

    # Build structured output
    treasury_tenors = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    treasury_yields = {t: rates.get(t, FALLBACK_RATES.get(t, 0.04) / 100)
                       for t in treasury_tenors if t in rates}

    money_market = {
        "SOFR":  rates.get("SOFR", FALLBACK_RATES["SOFR"] / 100),
        "EFFR":  rates.get("EFFR", FALLBACK_RATES["EFFR"] / 100),
    }

    # Build par rates dict for integer tenors (needed for curve bootstrapping)
    # Interpolate to get 4Y, 6Y, 8Y, 9Y from available tenors
    par_rates_integer = _interpolate_integer_tenors(treasury_yields)

    result = {
        "treasury_yields":   treasury_yields,
        "par_rates_integer": par_rates_integer,
        "money_market":      money_market,
        "source":            source,
        "fetched_at":        datetime.utcnow().isoformat() + "Z",
    }

    print(f"  Source: {source}")
    print(f"  10Y: {treasury_yields.get('10Y', 0)*100:.3f}%  "
          f"2Y: {treasury_yields.get('2Y', 0)*100:.3f}%  "
          f"SOFR: {money_market['SOFR']*100:.3f}%")
    return result


def _interpolate_integer_tenors(yields: Dict) -> Dict[int, float]:
    """
    Interpolate to produce par rates at every integer tenor 1-30.
    Required by bootstrap_par_curve which needs consecutive integers.
    """
    # Known tenors in years
    tenor_map = {"3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3,
                 "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}

    known = sorted([(tenor_map[k], v) for k, v in yields.items() if k in tenor_map])
    if not known:
        return {t: 0.04 for t in range(1, 31)}

    def interp(t: float) -> float:
        if t <= known[0][0]:
            return known[0][1]
        if t >= known[-1][0]:
            return known[-1][1]
        for (t0, r0), (t1, r1) in zip(known, known[1:]):
            if t0 <= t <= t1:
                frac = (t - t0) / (t1 - t0)
                return r0 + frac * (r1 - r0)
        return known[-1][1]

    return {t: interp(float(t)) for t in range(1, 31)}


def get_par_rates_for_curve(market_data: Dict, max_tenor: int = 10) -> Dict[int, float]:
    """Extract integer-tenor par rates suitable for yield curve bootstrapping."""
    par = market_data.get("par_rates_integer", {})
    return {t: par[t] for t in range(1, max_tenor + 1) if t in par}


if __name__ == "__main__":
    data = fetch_live_rates()
    print("\nTreasury Yields:")
    for tenor, rate in data["treasury_yields"].items():
        print(f"  {tenor:4}: {rate*100:.3f}%")
    print(f"\nSOFR: {data['money_market']['SOFR']*100:.3f}%")
    print(f"EFFR: {data['money_market']['EFFR']*100:.3f}%")
