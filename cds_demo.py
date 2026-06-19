"""
Demo: bootstrap a survival curve from market CDS par spreads, validate
that repricing each tenor reproduces its own input spread (proving the
bootstrap actually solved the par condition rather than just looking
plausible), then mark an existing off-market CDS position to that curve.

Run with: python3 cds_demo.py
"""

from yield_curve import bootstrap_par_curve
from cds_pricer import bootstrap_survival_curve, fair_spread, mtm_value


def main():
    par_rates = {1: 0.0480, 2: 0.0470, 3: 0.0460, 4: 0.0452, 5: 0.0445}
    discount_curve = bootstrap_par_curve(par_rates)

    # A rising credit curve: the market sees more default risk further out.
    cds_spreads = {1: 0.0080, 2: 0.0110, 3: 0.0135, 4: 0.0150, 5: 0.0160}
    recovery_rate = 0.40
    survival_curve = bootstrap_survival_curve(discount_curve, cds_spreads, recovery_rate)

    print("Bootstrapped survival curve:")
    for point in survival_curve.points:
        print(f"  {point.tenor:.0f}Y   survival={point.survival_probability:.4%}   "
              f"hazard={point.hazard_rate:.4%}")

    print("\nSanity check -- repricing each tenor's fair spread against its own input spread:")
    for n, input_spread in cds_spreads.items():
        repriced = fair_spread(discount_curve, survival_curve, n, recovery_rate)
        print(f"  {n}Y: input={input_spread:.4%}   repriced={repriced:.4%}")

    print("\nMark-to-market example:")
    print("  Bought $10,000,000 of 5Y protection a year ago at a contractual spread of 1.30%.")
    fair = fair_spread(discount_curve, survival_curve, 5, recovery_rate)
    print(f"  Today's 5Y fair spread on this curve: {fair:.2%}")
    value = mtm_value(discount_curve, survival_curve, maturity=5, contractual_spread=0.0130,
                       notional=10_000_000, buying_protection=True, recovery_rate=recovery_rate)
    print(f"  Mark-to-market value of the position: ${value:,.2f}")
    print("  (Positive because spreads widened since the trade was put on -- the protection")
    print("   you locked in cheaply is now worth more than what you're paying for it.)")


if __name__ == "__main__":
    main()
