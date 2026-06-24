"""
stress_tests.py
───────────────
Scenario analysis and stress testing for rates portfolios.

Scenarios:
  - Parallel shift (±25bp, ±50bp, ±100bp, ±200bp)
  - Curve steepener / flattener (short rates up, long rates down, and vice versa)
  - Bear steepener (long rates up more than short)
  - Bull flattener (long rates down more than short)
  - 2008 financial crisis (rates down 300bp)
  - 2022 Fed hike cycle (rates up 500bp)
  - Custom scenario

Runs each scenario across the full portfolio: bonds, swaps, options.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class StressScenario:
    name:        str
    description: str
    shifts:      Dict[int, float]   # tenor (years) -> rate shift in decimal


@dataclass
class ScenarioResult:
    scenario:       StressScenario
    base_npv:       float
    stressed_npv:   float
    pnl:            float
    pnl_bps:        float    # P&L as fraction of notional in bps


# ── Standard scenario library ─────────────────────────────────────────────────

def get_standard_scenarios() -> List[StressScenario]:
    tenors = list(range(1, 31))
    return [
        StressScenario("Parallel +25bp",  "+25bp parallel shift",  {t: +0.0025 for t in tenors}),
        StressScenario("Parallel -25bp",  "-25bp parallel shift",  {t: -0.0025 for t in tenors}),
        StressScenario("Parallel +50bp",  "+50bp parallel shift",  {t: +0.0050 for t in tenors}),
        StressScenario("Parallel -50bp",  "-50bp parallel shift",  {t: -0.0050 for t in tenors}),
        StressScenario("Parallel +100bp", "+100bp parallel shift", {t: +0.0100 for t in tenors}),
        StressScenario("Parallel -100bp", "-100bp parallel shift", {t: -0.0100 for t in tenors}),
        StressScenario("Parallel +200bp", "+200bp parallel shift", {t: +0.0200 for t in tenors}),
        StressScenario("Parallel -200bp", "-200bp parallel shift", {t: -0.0200 for t in tenors}),
        StressScenario(
            "Bear Steepener",
            "Short rates +50bp, long rates +150bp (bear steepening)",
            {t: +0.0050 + max(0, (t - 2) / 28) * 0.0100 for t in tenors}
        ),
        StressScenario(
            "Bull Flattener",
            "Short rates -25bp, long rates -100bp (bull flattening)",
            {t: -0.0025 - max(0, (t - 2) / 28) * 0.0075 for t in tenors}
        ),
        StressScenario(
            "Bear Flattener",
            "Short rates +150bp, long rates +50bp (Fed hiking)",
            {t: +0.0150 - max(0, (t - 2) / 28) * 0.0100 for t in tenors}
        ),
        StressScenario(
            "Bull Steepener",
            "Short rates -100bp, long rates flat (easing cycle)",
            {t: -0.0100 + max(0, (t - 2) / 28) * 0.0100 for t in tenors}
        ),
        StressScenario(
            "2008 Crisis",
            "300bp rate cut (GFC flight-to-quality)",
            {t: -0.0300 for t in tenors}
        ),
        StressScenario(
            "2022 Fed Hike Cycle",
            "500bp tightening (short end up 500bp, long end up 300bp)",
            {t: +0.0500 - max(0, (t - 2) / 28) * 0.0200 for t in tenors}
        ),
    ]


def stress_swap(
    par_rates: Dict[int, float],
    notional: float,
    fixed_rate: float,
    maturity_years: int,
    pay_fixed: bool,
    scenarios: Optional[List[StressScenario]] = None,
) -> List[ScenarioResult]:
    """Run stress scenarios on an IR swap."""
    from yield_curve import bootstrap_par_curve
    from swap_pricer import price_swap

    if scenarios is None:
        scenarios = get_standard_scenarios()

    base_curve  = bootstrap_par_curve(par_rates)
    base_result = price_swap(base_curve, par_rates, notional, fixed_rate, maturity_years, pay_fixed)
    base_npv    = base_result.npv

    results = []
    for scenario in scenarios:
        stressed_rates = {t: max(0.0001, par_rates.get(t, 0.04) + scenario.shifts.get(t, 0))
                         for t in par_rates}
        stressed_curve  = bootstrap_par_curve(stressed_rates)
        stressed_result = price_swap(stressed_curve, stressed_rates, notional, fixed_rate,
                                     maturity_years, pay_fixed)
        stressed_npv = stressed_result.npv
        pnl          = stressed_npv - base_npv
        pnl_bps      = (pnl / notional) * 10000

        results.append(ScenarioResult(
            scenario     = scenario,
            base_npv     = base_npv,
            stressed_npv = stressed_npv,
            pnl          = pnl,
            pnl_bps      = pnl_bps,
        ))

    return results


def stress_bond(
    par_rates: Dict[int, float],
    face_value: float,
    coupon_rate: float,
    years_to_maturity: float,
    scenarios: Optional[List[StressScenario]] = None,
) -> List[ScenarioResult]:
    """Run stress scenarios on a bond."""
    from yield_curve import bootstrap_par_curve
    from bond_pricer import price_bond

    if scenarios is None:
        scenarios = get_standard_scenarios()

    base_curve = bootstrap_par_curve(par_rates)
    base_price = price_bond(base_curve, face_value, coupon_rate, years_to_maturity)

    results = []
    for scenario in scenarios:
        stressed_rates = {t: max(0.0001, par_rates.get(t, 0.04) + scenario.shifts.get(t, 0))
                         for t in par_rates}
        stressed_curve = bootstrap_par_curve(stressed_rates)
        stressed_price = price_bond(stressed_curve, face_value, coupon_rate, years_to_maturity)
        pnl            = stressed_price - base_price
        pnl_bps        = (pnl / face_value) * 10000

        results.append(ScenarioResult(
            scenario     = scenario,
            base_npv     = base_price,
            stressed_npv = stressed_price,
            pnl          = pnl,
            pnl_bps      = pnl_bps,
        ))

    return results


def format_stress_results(results: List[ScenarioResult], instrument: str = "Position") -> str:
    lines = [
        f"\n{'═'*65}",
        f"  STRESS TEST RESULTS — {instrument}",
        f"{'═'*65}",
        f"  {'Scenario':<22} {'Base NPV':>12} {'Stressed':>12} {'P&L':>12} {'BPS':>8}",
        f"  {'-'*22} {'-'*12} {'-'*12} {'-'*12} {'-'*8}",
    ]
    for r in results:
        pnl_str = f"${r.pnl:>+,.0f}"
        bps_str = f"{r.pnl_bps:>+.1f}"
        indicator = "🔴" if r.pnl < -10000 else ("🟡" if r.pnl < 0 else "🟢")
        lines.append(
            f"  {r.scenario.name:<22} ${r.base_npv:>11,.0f} ${r.stressed_npv:>11,.0f} "
            f"{pnl_str:>12} {bps_str:>7} {indicator}"
        )
    lines.append(f"{'═'*65}\n")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from yield_curve import bootstrap_par_curve
    from market_data import fetch_live_rates, get_par_rates_for_curve
    from swap_pricer import price_swap

    data      = fetch_live_rates()
    par_rates = get_par_rates_for_curve(data, max_tenor=10)

    print("\nRunning stress tests on 10Y pay-fixed swap ($10M notional)...")
    fixed_rate = par_rates[10]
    results    = stress_swap(par_rates, 10_000_000, fixed_rate, 10, pay_fixed=True)
    print(format_stress_results(results, f"10Y IRS ${10_000_000:,} Pay Fixed @ {fixed_rate*100:.3f}%"))

    print("\nRunning stress tests on 10Y US Treasury bond ($1M face)...")
    bond_results = stress_bond(par_rates, 1_000_000, par_rates[10], 10)
    print(format_stress_results(bond_results, f"10Y UST ${1_000_000:,} Coupon {par_rates[10]*100:.3f}%"))
