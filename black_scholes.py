"""
Black-Scholes European option pricing and Greeks.

Implements the closed-form Black-Scholes formulas for price, delta, gamma,
vega, theta, and rho directly from the standard normal CDF and PDF, rather
than pulling them from a quant library, so the mechanics stay visible
instead of being a black box.
"""

import math


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (no scipy dependency)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _d1_d2(spot, strike, rate, vol, time):
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time) / (vol * math.sqrt(time))
    d2 = d1 - vol * math.sqrt(time)
    return d1, d2


def price(spot: float, strike: float, rate: float, vol: float, time: float,
           option_type: str = "call") -> float:
    """Black-Scholes price for a European call or put."""
    d1, d2 = _d1_d2(spot, strike, rate, vol, time)
    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * time) * _norm_cdf(d2)
    return strike * math.exp(-rate * time) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def greeks(spot: float, strike: float, rate: float, vol: float, time: float,
           option_type: str = "call") -> dict:
    """Analytical Greeks: delta, gamma, vega, theta, rho.

    Vega is scaled to the price change per 1 vol point (e.g. 0.25 -> 0.26),
    and theta is scaled to the price change per calendar day rather than
    per year, matching how these are typically quoted in practice.
    """
    d1, d2 = _d1_d2(spot, strike, rate, vol, time)
    pdf_d1 = _norm_pdf(d1)
    sqrt_t = math.sqrt(time)

    gamma = pdf_d1 / (spot * vol * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t / 100

    if option_type == "call":
        delta = _norm_cdf(d1)
        theta_annual = (-(spot * pdf_d1 * vol) / (2 * sqrt_t)
                         - rate * strike * math.exp(-rate * time) * _norm_cdf(d2))
        rho = strike * time * math.exp(-rate * time) * _norm_cdf(d2) / 100
    else:
        delta = _norm_cdf(d1) - 1
        theta_annual = (-(spot * pdf_d1 * vol) / (2 * sqrt_t)
                         + rate * strike * math.exp(-rate * time) * _norm_cdf(-d2))
        rho = -strike * time * math.exp(-rate * time) * _norm_cdf(-d2) / 100

    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta_annual / 365,
        "rho": rho,
    }
