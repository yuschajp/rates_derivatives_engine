"""
Demo: bootstrap a zero curve from par rates, price two bonds off it, and
compute DV01 and modified duration for each via shock-and-reprice.

Run with: python3 demo.py
"""

from yield_curve import bootstrap_par_curve
from bond_pricer import price_bond, dv01, modified_duration


def main():
    par_rates = {1: 0.0480, 2: 0.0470, 3: 0.0460, 4: 0.0452, 5: 0.0445}
    curve = bootstrap_par_curve(par_rates)

    print("Bootstrapped zero curve:")
    for point in curve.points:
        par = par_rates[int(point.tenor)]
        print(f"  {point.tenor:.0f}Y   par={par:.3%}   zero={point.zero_rate:.4%}   "
              f"DF={point.discount_factor:.6f}")

    print()
    for years, coupon in [(3, 0.05), (5, 0.045)]:
        price = price_bond(curve, 100, coupon, years)
        dv = dv01(par_rates, 100, coupon, years)
        dur = modified_duration(curve, par_rates, 100, coupon, years)
        print(f"{years}Y bond, {coupon:.2%} coupon:")
        print(f"  Price: {price:.4f}")
        print(f"  DV01: {dv:.4f} per 1bp")
        print(f"  Modified duration: {dur:.4f} years")
        print()


if __name__ == "__main__":
    main()
