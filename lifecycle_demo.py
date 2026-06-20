"""
End-to-end lifecycle demo: one corporate credit position, viewed three
different ways off the same discount curve -- interest rate risk on the
bond itself, an equity put already in place as a tail hedge, and what
direct CDS protection on the same issuer would look like instead.

Run with: python3 lifecycle_demo.py
"""

from yield_curve import bootstrap_par_curve
from bond_pricer import price_bond, dv01, modified_duration
from black_scholes import price as option_price, greeks as option_greeks
from cds_pricer import bootstrap_survival_curve, fair_spread, mtm_value


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main():
    section("1. Build the funding curve everything else gets priced off of")
    par_rates = {1: 0.0480, 2: 0.0470, 3: 0.0460, 4: 0.0452, 5: 0.0445}
    discount_curve = bootstrap_par_curve(par_rates)
    for point in discount_curve.points:
        print(f"  {point.tenor:.0f}Y   zero={point.zero_rate:.4%}   DF={point.discount_factor:.6f}")

    section("2. Price the bond position and measure its rate risk")
    notional = 10_000_000
    coupon_rate = 0.05
    maturity = 5
    price_pct = price_bond(discount_curve, 100, coupon_rate, maturity)
    position_value = notional * price_pct / 100
    position_dv01 = dv01(par_rates, 100, coupon_rate, maturity) * (notional / 100)
    position_duration = modified_duration(discount_curve, par_rates, 100, coupon_rate, maturity)
    print(f"  $10,000,000 notional, {maturity}Y {coupon_rate:.2%} corporate bond")
    print(f"  Price: {price_pct:.4f}   Position value: ${position_value:,.2f}")
    print(f"  Position DV01: ${position_dv01:,.2f} per 1bp")
    print(f"  Modified duration: {position_duration:.4f} years")

    section("3. Check the equity tail hedge already in place on the same issuer")
    spot, strike, rate, vol, time = 50, 40, 0.045, 0.35, 1.0
    put_price = option_price(spot, strike, rate, vol, time, "put")
    put_greeks = option_greeks(spot, strike, rate, vol, time, "put")
    contracts = 2_000  # 100 shares per contract
    hedge_cost = put_price * contracts * 100
    print(f"  Holding {contracts:,} put contracts, strike ${strike}, spot ${spot}, 1Y expiry")
    print(f"  Put price per share: ${put_price:.4f}   Total hedge cost: ${hedge_cost:,.2f}")
    print(f"  Delta: {put_greeks['delta']:+.4f}   Gamma: {put_greeks['gamma']:.5f}   "
          f"Vega: {put_greeks['vega']:.4f}")
    print("  If the stock drops further, this hedge gains value as delta moves toward -1.")

    section("4. Price out direct CDS protection on the same issuer instead")
    cds_spreads = {1: 0.0080, 2: 0.0110, 3: 0.0135, 4: 0.0150, 5: 0.0160}
    recovery_rate = 0.40
    survival_curve = bootstrap_survival_curve(discount_curve, cds_spreads, recovery_rate)
    current_fair_spread = fair_spread(discount_curve, survival_curve, maturity, recovery_rate)
    print(f"  Today's {maturity}Y fair CDS spread on this issuer: {current_fair_spread:.2%}")
    print(f"  Buying ${notional:,.0f} of {maturity}Y protection today would cost that spread annually.")

    print("\n  Suppose the desk actually bought this protection a year ago at 1.30%,")
    print("  and the credit curve has since widened to today's level:")
    value = mtm_value(discount_curve, survival_curve, maturity, contractual_spread=0.0130,
                       notional=notional, buying_protection=True, recovery_rate=recovery_rate)
    print(f"  Mark-to-market value of that protection today: ${value:,.2f}")
    print("  That gain offsets the bond position's own credit risk directly -- a different")
    print("  hedge than the equity put, but expressing a view on the same underlying name.")


if __name__ == "__main__":
    main()
