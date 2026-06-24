"""
swap_pricer.py
──────────────
Interest rate swap pricing and risk built on the existing yield_curve module.

Prices vanilla fixed-for-floating IRS:
  - NPV (mark to market)
  - Par swap rate (fair fixed rate)
  - DV01 by tenor bucket
  - PV01 (parallel shift sensitivity)
  - BPV (basis point value)

Methodology:
  Fixed leg: discount each fixed coupon payment
  Float leg: each float payment = (forward rate × notional × day fraction),
             discounted back. For a standard swap, float leg NPV = notional × (1 - DF(maturity))
             since reset-at-beginning / pay-at-end floating replicates a floater at par.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class SwapResult:
    npv:            float   # Net present value (pay fixed = negative if rates down)
    par_rate:       float   # Fair fixed rate that sets NPV to zero
    fixed_leg_pv:   float   # PV of fixed payments
    float_leg_pv:   float   # PV of floating payments
    dv01:           float   # Dollar value of 1bp parallel shift
    pv01:           float   # PV of 1bp on fixed rate only
    annuity:        float   # PV of 1 per period (fixed leg annuity factor)
    notional:       float
    maturity:       float
    fixed_rate:     float


def price_swap(
    curve,
    par_rates: Dict[int, float],
    notional: float,
    fixed_rate: float,
    maturity_years: float,
    pay_fixed: bool = True,
    freq: int = 2,          # semiannual by default
) -> SwapResult:
    """
    Price a vanilla fixed-for-floating interest rate swap.

    pay_fixed=True: we pay fixed, receive floating (typical hedge)
    pay_fixed=False: we receive fixed, pay floating
    """
    from yield_curve import bootstrap_par_curve

    dt       = 1.0 / freq
    n_periods = int(round(maturity_years * freq))

    # ── Fixed leg ─────────────────────────────────────────────────────────────
    fixed_coupon = notional * fixed_rate * dt
    fixed_leg_pv = sum(fixed_coupon * curve.discount_factor(i * dt)
                       for i in range(1, n_periods + 1))
    # Add notional at maturity (for NPV calculation, net against float notional)

    # ── Float leg ─────────────────────────────────────────────────────────────
    # For a reset-at-start floating leg: PV = notional × (1 - DF(T))
    # This is exact for a standard LIBOR/SOFR flat floating leg
    float_leg_pv = notional * (1.0 - curve.discount_factor(maturity_years))

    # ── NPV ───────────────────────────────────────────────────────────────────
    if pay_fixed:
        npv = float_leg_pv - fixed_leg_pv
    else:
        npv = fixed_leg_pv - float_leg_pv

    # ── Par rate ──────────────────────────────────────────────────────────────
    # Par rate = float leg PV / annuity
    annuity = sum(dt * curve.discount_factor(i * dt) for i in range(1, n_periods + 1))
    par_rate = float_leg_pv / (notional * annuity) if annuity > 0 else fixed_rate

    # ── DV01 (parallel curve shift) ───────────────────────────────────────────
    bump = 0.0001  # 1bp
    up_rates   = {t: r + bump for t, r in par_rates.items()}
    down_rates = {t: r - bump for t, r in par_rates.items()}

    up_curve   = bootstrap_par_curve(up_rates)
    down_curve = bootstrap_par_curve(down_rates)

    def _npv(c):
        fl = notional * (1.0 - c.discount_factor(maturity_years))
        fx = sum(fixed_coupon * c.discount_factor(i * dt) for i in range(1, n_periods + 1))
        return fl - fx if pay_fixed else fx - fl

    dv01 = (_npv(down_curve) - _npv(up_curve)) / 2

    # ── PV01 (fixed rate sensitivity only) ───────────────────────────────────
    pv01 = notional * annuity * 0.0001

    return SwapResult(
        npv          = npv,
        par_rate     = par_rate,
        fixed_leg_pv = fixed_leg_pv,
        float_leg_pv = float_leg_pv,
        dv01         = dv01,
        pv01         = pv01,
        annuity      = annuity,
        notional     = notional,
        maturity     = maturity_years,
        fixed_rate   = fixed_rate,
    )


def dv01_by_tenor_bucket(
    par_rates: Dict[int, float],
    notional: float,
    fixed_rate: float,
    maturity_years: int,
    pay_fixed: bool = True,
    freq: int = 2,
    bump: float = 0.0001,
) -> Dict[str, float]:
    """
    Compute DV01 contribution by tenor bucket (key rate durations).
    Bumps each tenor individually rather than a parallel shift.
    """
    from yield_curve import bootstrap_par_curve

    base_curve = bootstrap_par_curve(par_rates)
    base_result = price_swap(base_curve, par_rates, notional, fixed_rate, maturity_years, pay_fixed, freq)
    base_npv    = base_result.npv

    buckets = {}
    for tenor in sorted(par_rates.keys()):
        bumped = {t: r + (bump if t == tenor else 0) for t, r in par_rates.items()}
        bumped_curve  = bootstrap_par_curve(bumped)
        bumped_result = price_swap(bumped_curve, bumped, notional, fixed_rate, maturity_years, pay_fixed, freq)
        buckets[f"{tenor}Y"] = bumped_result.npv - base_npv

    return buckets


def format_swap_result(result: SwapResult, pay_fixed: bool = True) -> str:
    direction = "Pay Fixed / Receive Float" if pay_fixed else "Receive Fixed / Pay Float"
    in_the_money = result.npv > 0
    return f"""
╔══════════════════════════════════════════════════════════════╗
║           IR SWAP PRICING SUMMARY                            ║
╚══════════════════════════════════════════════════════════════╝
Direction    : {direction}
Notional     : ${result.notional:>15,.0f}
Maturity     : {result.maturity:.1f} years
Fixed Rate   : {result.fixed_rate*100:.4f}%
Par Rate     : {result.par_rate*100:.4f}%   ({'above' if result.fixed_rate > result.par_rate else 'below'} market)

PV BREAKDOWN
────────────
Fixed Leg PV : ${result.fixed_leg_pv:>15,.2f}
Float Leg PV : ${result.float_leg_pv:>15,.2f}
NPV          : ${result.npv:>15,.2f}   {'(ITM ✅)' if in_the_money else '(OTM ❌)'}

RISK METRICS
────────────
DV01         : ${result.dv01:>12,.2f}   (per 1bp parallel shift)
PV01         : ${result.pv01:>12,.2f}   (per 1bp on fixed rate)
Annuity      : {result.annuity:.6f}
═══════════════════════════════════════════════════════════════
""".strip()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from yield_curve import bootstrap_par_curve
    from market_data import fetch_live_rates, get_par_rates_for_curve

    data      = fetch_live_rates()
    par_rates = get_par_rates_for_curve(data, max_tenor=10)
    curve     = bootstrap_par_curve(par_rates)

    # Price a 10Y pay-fixed swap at current market rate
    result = price_swap(
        curve      = curve,
        par_rates  = par_rates,
        notional   = 10_000_000,
        fixed_rate = par_rates[10],   # at-market
        maturity_years = 10,
        pay_fixed  = True,
    )

    print(format_swap_result(result))

    print("\nDV01 by Tenor Bucket:")
    buckets = dv01_by_tenor_bucket(par_rates, 10_000_000, par_rates[10], 10)
    for bucket, dv in buckets.items():
        bar = "█" * max(1, int(abs(dv) * 500))
        print(f"  {bucket:4}: ${dv:>8.2f}  {bar}")
