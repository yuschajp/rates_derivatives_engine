"""
Generates a static HTML dashboard from the rates and derivatives engine:
the bootstrapped yield curve, a priced bond position with its risk, the
options Greeks across strikes, and the CDS survival curve with its
repricing validation, all on one page you open directly in a browser,
no server required.

Run with: python3 dashboard.py
Then open dashboard.html in any browser.
"""

import html

from yield_curve import bootstrap_par_curve
from bond_pricer import price_bond, dv01, modified_duration
from black_scholes import price as option_price, greeks as option_greeks
from cds_pricer import bootstrap_survival_curve, fair_spread


def render_table(headers, rows):
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{html.escape('' if v is None else str(v))}</td>" for v in row)
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_data():
    par_rates = {1: 0.0480, 2: 0.0470, 3: 0.0460, 4: 0.0452, 5: 0.0445}
    discount_curve = bootstrap_par_curve(par_rates)
    curve_rows = [
        (f"{p.tenor:.0f}Y", f"{par_rates[int(p.tenor)]:.3%}", f"{p.zero_rate:.4%}", f"{p.discount_factor:.6f}")
        for p in discount_curve.points
    ]

    notional, coupon_rate, maturity = 10_000_000, 0.05, 5
    price_pct = price_bond(discount_curve, 100, coupon_rate, maturity)
    position_value = notional * price_pct / 100
    position_dv01 = dv01(par_rates, 100, coupon_rate, maturity) * (notional / 100)
    duration = modified_duration(discount_curve, par_rates, 100, coupon_rate, maturity)

    spot, rate, vol, time = 100, 0.04, 0.25, 0.5
    strikes = [85, 100, 115]
    greek_rows = []
    for opt_type in ("call", "put"):
        for strike in strikes:
            g = option_greeks(spot, strike, rate, vol, time, opt_type)
            p = option_price(spot, strike, rate, vol, time, opt_type)
            greek_rows.append((
                opt_type.upper(), strike, f"{p:.3f}", f"{g['delta']:+.4f}",
                f"{g['gamma']:.5f}", f"{g['vega']:.4f}", f"{g['theta']:+.4f}", f"{g['rho']:+.4f}",
            ))

    cds_spreads = {1: 0.0080, 2: 0.0110, 3: 0.0135, 4: 0.0150, 5: 0.0160}
    recovery_rate = 0.40
    survival_curve = bootstrap_survival_curve(discount_curve, cds_spreads, recovery_rate)
    cds_rows = []
    for point in survival_curve.points:
        n = int(point.tenor)
        repriced = fair_spread(discount_curve, survival_curve, n, recovery_rate)
        cds_rows.append((
            f"{n}Y", f"{cds_spreads[n]:.4%}", f"{repriced:.4%}",
            f"{point.survival_probability:.4%}", f"{point.hazard_rate:.4%}",
        ))

    return {
        "curve_rows": curve_rows,
        "position_value": position_value,
        "position_dv01": position_dv01,
        "duration": duration,
        "notional": notional,
        "coupon_rate": coupon_rate,
        "maturity": maturity,
        "greek_rows": greek_rows,
        "cds_rows": cds_rows,
    }


def build_html(data):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Rates & Derivatives Engine Dashboard</title>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; background: #f5f6f8; color: #1a1a1a; margin: 0; padding: 32px; }}
  h1 {{ color: #1B3A5C; margin-bottom: 4px; }}
  .subtitle {{ color: #5a5a5a; margin-bottom: 28px; }}
  .source-link {{ display: inline-block; margin-bottom: 20px; font-size: 13px; }}
  .source-link a {{ color: #1B3A5C; text-decoration: none; font-weight: 600; }}
  .source-link a:hover {{ text-decoration: underline; }}
  .card {{ background: #ffffff; border-radius: 8px; padding: 20px 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card h2 {{ color: #1B3A5C; font-size: 16px; margin-top: 0; border-bottom: 1px solid #e2e2e2; padding-bottom: 8px; }}
  .figure-row {{ }}
  .figure-block {{ display: inline-block; margin-right: 48px; vertical-align: top; }}
  .figure {{ font-size: 24px; font-weight: 600; color: #1B3A5C; }}
  .figure-label {{ font-size: 12px; color: #5a5a5a; margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; background: #1B3A5C; color: #fff; padding: 8px 10px; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #ececec; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
</style>
</head>
<body>
  <h1>Rates & Derivatives Engine</h1>
  <div class="subtitle">Bootstrapped curve, bond risk, options Greeks, and CDS pricing</div>
  <div class="source-link"><a href="https://github.com/yuschajp/rates_derivatives_engine">View source on GitHub &rarr;</a></div>

  <div class="card">
    <h2>Bootstrapped zero curve</h2>
    {render_table(["Tenor", "Par rate", "Zero rate", "Discount factor"], data["curve_rows"])}
  </div>

  <div class="card">
    <h2>Bond position</h2>
    <div class="figure-row">
      <div class="figure-block">
        <div class="figure-label">${data['notional']:,.0f} notional, {data['maturity']}Y {data['coupon_rate']:.2%} coupon</div>
        <div class="figure">${data['position_value']:,.2f}</div>
      </div>
      <div class="figure-block">
        <div class="figure-label">DV01 per 1bp</div>
        <div class="figure">${data['position_dv01']:,.2f}</div>
      </div>
      <div class="figure-block">
        <div class="figure-label">Modified duration</div>
        <div class="figure">{data['duration']:.4f}y</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Options Greeks across strikes</h2>
    {render_table(["Type", "Strike", "Price", "Delta", "Gamma", "Vega", "Theta", "Rho"], data["greek_rows"])}
  </div>

  <div class="card">
    <h2>CDS survival curve and repricing check</h2>
    {render_table(["Tenor", "Input spread", "Repriced spread", "Survival prob.", "Hazard rate"], data["cds_rows"])}
  </div>
</body>
</html>"""


def main():
    data = build_data()
    output = build_html(data)
    with open("dashboard.html", "w") as f:
        f.write(output)
    print("Wrote dashboard.html -- open it in your browser to view it.")


if __name__ == "__main__":
    main()
