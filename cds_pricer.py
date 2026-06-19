"""
Simplified CDS (credit default swap) pricing: survival curve bootstrapping
from market par spreads, fair spread calculation, and mark-to-market
valuation for an existing position.

Built directly on top of the yield curve module -- CDS valuation needs a
discount curve for both legs, and reusing the existing discount curve
here keeps the rates engine's pieces connected rather than duplicated.

Simplifications relative to the full ISDA standard model: annual premium
payments rather than quarterly, and no accrued-premium-on-default
adjustment. The actual methodology -- bootstrapping survival probabilities
so each tenor reprices to its own par spread, then using that curve to
price the premium and protection legs of any contract -- is real.
"""

import math
from dataclasses import dataclass


@dataclass
class SurvivalPoint:
    tenor: float
    survival_probability: float
    hazard_rate: float  # piecewise-constant hazard rate for the period ending at this tenor


class SurvivalCurve:
    def __init__(self, points: list):
        self.points = sorted(points, key=lambda p: p.tenor)

    def survival_probability(self, t: float) -> float:
        """Survival probability at time t, using the piecewise-constant
        hazard rate of whichever bootstrapped period t falls into."""
        if t <= 0:
            return 1.0
        prev_tenor, prev_q = 0.0, 1.0
        for p in self.points:
            if t <= p.tenor:
                return prev_q * math.exp(-p.hazard_rate * (t - prev_tenor))
            prev_tenor, prev_q = p.tenor, p.survival_probability
        last = self.points[-1]
        return last.survival_probability * math.exp(-last.hazard_rate * (t - last.tenor))


def bootstrap_survival_curve(discount_curve, cds_spreads: dict, recovery_rate: float = 0.40) -> SurvivalCurve:
    """Bootstrap a survival curve from annual-pay par CDS spreads.

    cds_spreads: {tenor_in_whole_years: par_spread}, must include every
    integer year from 1 to the longest tenor, same convention as the
    yield curve bootstrap. discount_curve discounts both legs.

    At each tenor n, the par condition is that the premium leg and
    protection leg have equal present value:
        spread_n * annuity(n) == (1 - recovery) * protection(n)
    where annuity(n) and protection(n) both depend on survival
    probabilities up to and including the unknown Q(n). Solving that
    equation for Q(n) at each step, using only the *current* tenor's own
    spread (each tenor is a separate par contract, not a shared coupon
    schedule), is what makes this a bootstrap rather than a single solve.
    """
    tenors = sorted(cds_spreads.keys())
    if tenors != list(range(1, tenors[-1] + 1)):
        raise ValueError("cds_spreads must include every integer year from 1 to the longest tenor")

    points = []
    prev_tenor, prev_q = 0.0, 1.0
    protection_sum_known = 0.0   # running sum, already weighted by (1 - recovery_rate)
    annuity_sum_known = 0.0      # running sum, NOT weighted by any spread

    for n in tenors:
        spread = cds_spreads[n]
        df_n = discount_curve.discount_factor(n)
        delta_t = n - prev_tenor

        numerator = (protection_sum_known + (1 - recovery_rate) * df_n * prev_q
                     - spread * annuity_sum_known)
        denominator = df_n * (spread * delta_t + (1 - recovery_rate))
        q_n = numerator / denominator

        hazard_rate = -math.log(q_n / prev_q) / delta_t if prev_q > 0 else 0.0
        points.append(SurvivalPoint(tenor=float(n), survival_probability=q_n, hazard_rate=hazard_rate))

        protection_sum_known += (1 - recovery_rate) * df_n * (prev_q - q_n)
        annuity_sum_known += df_n * q_n * delta_t

        prev_tenor, prev_q = float(n), q_n

    return SurvivalCurve(points)


def risky_annuity(discount_curve, survival_curve, maturity: float, freq: int = 1) -> float:
    """PV01 of the premium leg: present value of 1 unit of spread paid
    while the reference entity survives, per unit notional."""
    n_payments = int(round(maturity * freq))
    total = 0.0
    prev_t = 0.0
    for i in range(1, n_payments + 1):
        t = i / freq
        delta_t = t - prev_t
        total += discount_curve.discount_factor(t) * survival_curve.survival_probability(t) * delta_t
        prev_t = t
    return total


def protection_leg_pv(discount_curve, survival_curve, maturity: float,
                       recovery_rate: float = 0.40, freq: int = 1) -> float:
    """Present value of the protection payment, paid (1 - recovery) times
    notional at the moment of default, per unit notional."""
    n_payments = int(round(maturity * freq))
    total = 0.0
    prev_q = 1.0
    for i in range(1, n_payments + 1):
        t = i / freq
        q = survival_curve.survival_probability(t)
        total += discount_curve.discount_factor(t) * (prev_q - q)
        prev_q = q
    return (1 - recovery_rate) * total


def fair_spread(discount_curve, survival_curve, maturity: float,
                 recovery_rate: float = 0.40, freq: int = 1) -> float:
    """The par spread at which the premium and protection legs balance."""
    annuity = risky_annuity(discount_curve, survival_curve, maturity, freq)
    protection = protection_leg_pv(discount_curve, survival_curve, maturity, recovery_rate, freq)
    return protection / annuity


def mtm_value(discount_curve, survival_curve, maturity: float, contractual_spread: float,
              notional: float, buying_protection: bool = True,
              recovery_rate: float = 0.40, freq: int = 1) -> float:
    """Mark-to-market value of an existing CDS position.

    Buying protection profits when the fair/par spread rises above the
    contractual spread you locked in -- the protection you're holding has
    become more valuable as the market prices in more default risk.
    Selling protection profits in the opposite direction.
    """
    annuity = risky_annuity(discount_curve, survival_curve, maturity, freq)
    current_fair_spread = fair_spread(discount_curve, survival_curve, maturity, recovery_rate, freq)
    value = (current_fair_spread - contractual_spread) * annuity * notional
    return value if buying_protection else -value
