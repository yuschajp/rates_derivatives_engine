"""
Bond pricing and risk (DV01, modified duration) off a bootstrapped curve.

DV01 and duration are computed by shock-and-reprice: bump every point on
the input par curve up and down by 1bp, rebuild the curve each time, and
reprice the bond off each shocked curve. This is the same parallel-shift
methodology production risk systems use for rate sensitivity, just
implemented directly instead of treated as a black box.
"""

from yield_curve import bootstrap_par_curve


def price_bond(curve, face_value: float, coupon_rate: float, years_to_maturity: float, freq: int = 1) -> float:
    """Price a bond off a given curve.

    coupon_rate: annual coupon rate (e.g. 0.045 for 4.5%).
    freq: payments per year (1 = annual, 2 = semiannual).
    """
    coupon = face_value * coupon_rate / freq
    n_payments = int(round(years_to_maturity * freq))
    pv = 0.0
    for i in range(1, n_payments + 1):
        t = i / freq
        cash_flow = coupon + (face_value if i == n_payments else 0.0)
        pv += cash_flow * curve.discount_factor(t)
    return pv


def dv01(par_rates: dict, face_value: float, coupon_rate: float, years_to_maturity: float,
         freq: int = 1, bump: float = 0.0001) -> float:
    """Price change for a 1bp parallel shift down, via central difference.

    Bumps every point on the par curve up and down by `bump` (1bp by
    default), rebuilds the curve under each scenario, and reprices the
    bond off each one. The result is the price change per 1bp move.
    """
    up_rates = {t: r + bump for t, r in par_rates.items()}
    down_rates = {t: r - bump for t, r in par_rates.items()}

    price_up = price_bond(bootstrap_par_curve(up_rates), face_value, coupon_rate, years_to_maturity, freq)
    price_down = price_bond(bootstrap_par_curve(down_rates), face_value, coupon_rate, years_to_maturity, freq)

    return (price_down - price_up) / 2


def modified_duration(curve, par_rates: dict, face_value: float, coupon_rate: float,
                       years_to_maturity: float, freq: int = 1) -> float:
    """Modified duration derived directly from DV01 and price.

    DV01 is the price change per 1bp (0.0001 in yield), so dP/dy = -DV01 / 0.0001,
    and modified duration D = -(1/P)(dP/dy) = (DV01 / price) * 10000.
    """
    price = price_bond(curve, face_value, coupon_rate, years_to_maturity, freq)
    dv = dv01(par_rates, face_value, coupon_rate, years_to_maturity, freq)
    return (dv / price) * 10000
