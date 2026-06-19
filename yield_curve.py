"""
Yield curve bootstrapping.

Builds a zero-coupon discount curve from a set of annual-pay par market
rates using standard bootstrapping: each year's discount factor is solved
for using the prior years' already-known discount factors, since a par
bond's price (100) must equal the present value of its own coupons plus
principal.

par_rates must include every integer year from 1 up to the longest tenor,
since the bootstrap for year N depends on having already solved years
1 through N-1.
"""

import math
from dataclasses import dataclass


@dataclass
class CurvePoint:
    tenor: float              # in years
    discount_factor: float
    zero_rate: float          # continuously compounded


class YieldCurve:
    def __init__(self, points: list):
        self.points = sorted(points, key=lambda p: p.tenor)

    def discount_factor(self, t: float) -> float:
        """Discount factor at time t, log-linearly interpolated between curve
        points and flat-extrapolated beyond either end using the nearest
        zero rate."""
        if t <= 0:
            return 1.0
        if t <= self.points[0].tenor:
            return math.exp(-self.points[0].zero_rate * t)
        if t >= self.points[-1].tenor:
            return math.exp(-self.points[-1].zero_rate * t)
        for p0, p1 in zip(self.points, self.points[1:]):
            if p0.tenor <= t <= p1.tenor:
                frac = (t - p0.tenor) / (p1.tenor - p0.tenor)
                log_df = (1 - frac) * math.log(p0.discount_factor) + frac * math.log(p1.discount_factor)
                return math.exp(log_df)
        raise ValueError(f"tenor {t} out of bounds")

    def zero_rate(self, t: float) -> float:
        if t <= 0:
            return self.points[0].zero_rate
        return -math.log(self.discount_factor(t)) / t


def bootstrap_par_curve(par_rates: dict) -> YieldCurve:
    """Bootstrap a zero curve from annual-pay par rates.

    par_rates: {tenor_in_whole_years: par_rate}, e.g. {1: 0.048, 2: 0.047,
    3: 0.046}. Must include every integer year from 1 to the longest tenor.
    """
    tenors = sorted(par_rates.keys())
    if tenors != list(range(1, tenors[-1] + 1)):
        raise ValueError("par_rates must include every integer year from 1 to the longest tenor")

    discount_factors = {}
    for n in tenors:
        coupon = par_rates[n] * 100
        pv_of_prior_coupons = sum(coupon * discount_factors[i] for i in range(1, n))
        # Par condition: 100 = pv_of_prior_coupons + (100 + coupon) * DF(n)
        discount_factors[n] = (100 - pv_of_prior_coupons) / (100 + coupon)

    points = []
    for n in tenors:
        df = discount_factors[n]
        zero = -math.log(df) / n
        points.append(CurvePoint(tenor=float(n), discount_factor=df, zero_rate=zero))
    return YieldCurve(points)
