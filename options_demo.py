"""
Demo: Black-Scholes pricing and Greeks across three strikes for both calls
and puts, plus a finite-difference check that the analytical delta matches
a numerical bump-and-reprice estimate.

Run with: python3 options_demo.py
"""

from black_scholes import price, greeks


def moneyness_label(spot: float, strike: float, option_type: str) -> str:
    """ITM/OTM flips between calls and puts -- a call is ITM when the
    strike is below spot, a put is ITM when the strike is above spot."""
    if option_type == "call":
        if strike < spot:
            return "ITM"
        if strike > spot:
            return "OTM"
        return "ATM"
    else:
        if strike > spot:
            return "ITM"
        if strike < spot:
            return "OTM"
        return "ATM"


def finite_difference_delta(spot, strike, rate, vol, time, option_type, bump=0.01):
    up = price(spot + bump, strike, rate, vol, time, option_type)
    down = price(spot - bump, strike, rate, vol, time, option_type)
    return (up - down) / (2 * bump)


def main():
    spot, rate, vol, time = 100, 0.04, 0.25, 0.5  # 6-month expiry, 25% vol, 4% rate
    strikes = [85, 100, 115]

    for option_type in ("call", "put"):
        print(f"--- {option_type.upper()} options, spot={spot}, vol={vol:.0%}, "
              f"{time*12:.0f}-month expiry ---")
        for strike in strikes:
            label = moneyness_label(spot, strike, option_type)
            p = price(spot, strike, rate, vol, time, option_type)
            g = greeks(spot, strike, rate, vol, time, option_type)
            print(f"  K={strike:3} ({label:3}): price={p:6.3f}  delta={g['delta']:+.4f}  "
                  f"gamma={g['gamma']:.5f}  vega={g['vega']:.4f}  "
                  f"theta={g['theta']:+.4f}  rho={g['rho']:+.4f}")
        print()

    print("Sanity check -- analytical delta vs. finite-difference delta:")
    for option_type in ("call", "put"):
        analytical = greeks(spot, 100, rate, vol, time, option_type)["delta"]
        numerical = finite_difference_delta(spot, 100, rate, vol, time, option_type)
        print(f"  {option_type:4}: analytical={analytical:+.5f}   "
              f"finite-difference={numerical:+.5f}")


if __name__ == "__main__":
    main()
