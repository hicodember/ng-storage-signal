"""Write a single self-contained HTML dashboard (no internet or libraries needed to open it)."""
import html
from datetime import date

import numpy as np
import pandas as pd


def _pct(x, d=1):
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{d}f}%"


def _num(x, d=2):
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{d}f}"


def _line_chart(series_list, w=760, h=260, pad=44):
    """series_list: [(label, color, pd.Series of equity indexed by date)]"""
    allv = pd.concat([s for _, _, s in series_list])
    xs = pd.to_datetime(pd.Index(allv.index))
    x0, x1 = xs.min().value, xs.max().value
    y0, y1 = float(allv.min()), float(allv.max())
    y0, y1 = min(y0, 1.0), max(y1, 1.0)
    span = (y1 - y0) or 1
    y0, y1 = y0 - span * 0.05, y1 + span * 0.05

    def X(t):
        return pad + (pd.Timestamp(t).value - x0) / ((x1 - x0) or 1) * (w - pad - 12)

    def Y(v):
        return h - pad + 10 - (v - y0) / (y1 - y0) * (h - pad - 10)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in range(5):
        v = y0 + (y1 - y0) * k / 4
        parts.append(f'<line x1="{pad}" x2="{w-12}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{pad-6}" y="{Y(v)+4:.1f}" class="tick" text-anchor="end">{(v-1)*100:+.0f}%</text>')
    parts.append(f'<line x1="{pad}" x2="{w-12}" y1="{Y(1):.1f}" y2="{Y(1):.1f}" class="base"/>')
    for yr in range(pd.Timestamp(x0).year + 1, pd.Timestamp(x1).year + 1, 2):
        t = pd.Timestamp(f"{yr}-01-01")
        parts.append(f'<text x="{X(t):.1f}" y="{h-12}" class="tick" text-anchor="middle">{yr}</text>')
    for label, color, s in series_list:
        pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s.items())
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
    parts.append("</svg>")
    legend = "".join(f'<span><i style="background:{c}"></i>{html.escape(l)}</span>' for l, c, _ in series_list)
    return f'<div class="legend">{legend}</div>' + "".join(parts)


def _scatter(xv, yv, w=760, h=260, pad=44):
    xv, yv = np.asarray(xv, float), np.asarray(yv, float)
    xm = max(np.nanpercentile(np.abs(xv), 99), 1e-9)
    ym = max(np.nanpercentile(np.abs(yv), 99), 1e-9)

    def X(v):
        return pad + (np.clip(v, -xm, xm) + xm) / (2 * xm) * (w - pad - 12)

    def Y(v):
        return h - pad + 10 - (np.clip(v, -ym, ym) + ym) / (2 * ym) * (h - pad - 10)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">',
             f'<line x1="{X(0):.1f}" x2="{X(0):.1f}" y1="10" y2="{h-pad+10}" class="base"/>',
             f'<line x1="{pad}" x2="{w-12}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" class="base"/>',
             f'<text x="{w-14}" y="{h-12}" class="tick" text-anchor="end">more gas than normal &#8594;</text>',
             f'<text x="{pad}" y="{h-12}" class="tick">&#8592; less gas than normal</text>',
             f'<text x="{pad+4}" y="20" class="tick">price up</text>',
             f'<text x="{pad+4}" y="{h-pad+4}" class="tick">price down</text>']
    for a, b in zip(xv, yv):
        if np.isfinite(a) and np.isfinite(b):
            parts.append(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="2.6" class="dot"/>')
    ok = np.isfinite(xv) & np.isfinite(yv)
    if ok.sum() > 10:
        m, c = np.polyfit(xv[ok], yv[ok], 1)
        parts.append(f'<line x1="{X(-xm):.1f}" y1="{Y(m*-xm+c):.1f}" x2="{X(xm):.1f}" y2="{Y(m*xm+c):.1f}" class="fit"/>')
    parts.append("</svg>")
    return "".join(parts)


def _bars(series_list, w=760, h=230, pad=44):
    """Grouped bars: [(label, color, pd.Series indexed by hold days)]"""
    keys = list(series_list[0][2].index)
    vals = np.concatenate([np.asarray(s.values, float) for _, _, s in series_list])
    m = max(np.nanmax(np.abs(vals)), 1e-9) * 1.15
    slot = (w - pad - 12) / len(keys)
    bw = slot * 0.8 / len(series_list)

    def Y(v):
        return 14 + (m - v) / (2 * m) * (h - pad - 14)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for k in (-1, -0.5, 0, 0.5, 1):
        v = m * k / 1.15
        parts.append(f'<line x1="{pad}" x2="{w-12}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="{'base' if k == 0 else 'grid'}"/>'
                     f'<text x="{pad-6}" y="{Y(v)+4:.1f}" class="tick" text-anchor="end">{v*100:+.1f}%</text>')
    for j, key in enumerate(keys):
        x = pad + j * slot + slot * 0.1
        for q, (_, color, s) in enumerate(series_list):
            v = float(s.get(key, np.nan))
            if not np.isfinite(v):
                continue
            y, y0 = Y(v), Y(0)
            parts.append(f'<rect x="{x + q*bw:.1f}" y="{min(y, y0):.1f}" width="{bw-2:.1f}" height="{abs(y0-y):.1f}" fill="{color}"/>')
        parts.append(f'<text x="{pad + j*slot + slot/2:.1f}" y="{h-pad+20}" class="tick" text-anchor="middle">{key}d</text>')
    parts.append(f'<text x="{(w+pad)/2:.1f}" y="{h-6}" class="tick" text-anchor="middle">trading days after the report</text></svg>')
    legend = "".join(f'<span><i style="background:{c}"></i>{html.escape(l)}</span>' for l, c, _ in series_list)
    return f'<div class="legend">{legend}</div>' + "".join(parts)


def _stat_cards(s, label):
    if s.get("trades", 0) == 0:
        return f"<p>No trades in the {label} period.</p>"
    cards = [("Trades", str(s["trades"])), ("Hit rate", _pct(s["hit_rate"], 0)),
             ("Avg trade", _pct(s["avg_trade"], 2)), ("Total return", _pct(s["total_return"], 0)),
             ("Sharpe", _num(s["sharpe"])), ("Max drawdown", _pct(s["max_drawdown"], 0)),
             ("t-stat", _num(s["t_stat"]))]
    return '<div class="cards">' + "".join(
        f'<div class="card"><b>{k}</b><span>{v}</span></div>' for k, v in cards) + "</div>"


def write_report(path, ctx):
    demo = ctx["demo"]
    tr, te = ctx["train_trades"], ctx["test_trades"]
    eq_train = (1 + tr.set_index(pd.to_datetime(tr["exit"]))["return"]).cumprod() if not tr.empty else pd.Series(dtype=float)
    start = eq_train.iloc[-1] if len(eq_train) else 1.0
    eq_test = start * (1 + te.set_index(pd.to_datetime(te["exit"]))["return"]).cumprod() if not te.empty else pd.Series(dtype=float)
    series = [s for s in [("Training period (settings chosen here)", "#9a9a9a", eq_train),
                          ("Test period (never seen while tuning)", "#d9541e", eq_test)] if len(s[2])]
    equity_svg = _line_chart(series) if series else "<p>No trades.</p>"
    scatter_svg = _scatter(ctx["reaction"]["surprise_z"], ctx["reaction"]["next_return"])

    decay_svg = _bars([("Training period", "#9a9a9a", ctx["decay_train"]),
                       ("Test period", "#d9541e", ctx["decay_test"])])
    pct_beat = ctx["baseline_pct"]
    grid = ctx["grid"].pivot(index="threshold", columns="hold_days", values="sharpe")
    grid_html = "<table class='grid'><tr><th>Threshold \\ Hold days</th>" + "".join(
        f"<th>{c}</th>" for c in grid.columns) + "</tr>"
    for th, row in grid.iterrows():
        grid_html += f"<tr><th>{th}</th>" + "".join(
            f"<td class='{'pick' if (th == ctx['threshold'] and c == ctx['hold_days']) else ''}'>{_num(v)}</td>"
            for c, v in row.items()) + "</tr>"
    grid_html += "</table>"

    last = te.tail(12).iloc[::-1] if not te.empty else tr.tail(12).iloc[::-1]
    trades_html = "<table class='trades'><tr><th>Report</th><th>Entry</th><th>Exit</th><th>Side</th><th>Contract traded</th><th>Legs</th><th>Surprise (z)</th><th>Size</th><th>Return</th></tr>" + "".join(
        f"<tr><td>{r.report_day}</td><td>{r.entry}</td><td>{r.exit}</td><td>{r.direction}</td>"
        f"<td>{r.contract}</td><td>{r.legs}</td><td>{r.surprise_z}</td><td>{r['size']}x</td><td class='{'pos' if r['return'] > 0 else 'neg'}'>{_pct(r['return'], 2)}</td></tr>"
        for _, r in last.iterrows()) + "</table>"

    banner = ('<div class="demo">DEMO DATA. These numbers come from simulated data used to test the code. '
              'Run <code>python run.py</code> to produce real results from EIA data.</div>') if demo else ""

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gas Storage Signal</title>
<style>
:root{{--ink:#141414;--muted:#5d5d5d;--rule:#e4e4e4;--accent:#d9541e;--bg:#fff;--soft:#f7f7f7}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Inter,Helvetica,Arial,sans-serif}}
main{{max-width:880px;margin:0 auto;padding:28px 16px 60px}}
.eyebrow{{color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}}
h1{{font-size:30px;margin:4px 0 6px;letter-spacing:-.02em}} h2{{font-size:19px;margin:34px 0 8px;border-bottom:1px solid var(--rule);padding-bottom:6px}}
.lead{{color:var(--muted);margin:0 0 6px}} .demo{{background:#fff4e5;border:1px solid #f0b37e;color:#8a3d0f;padding:10px 12px;border-radius:6px;margin:14px 0;font-weight:600}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;margin:8px 0}}
.card{{background:var(--soft);border-radius:6px;padding:8px 10px}} .card b{{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}} .card span{{font-size:19px;font-weight:700}}
.chart{{width:100%;height:auto;display:block}} .grid line,.chart .grid{{stroke:#eee}} .chart .base{{stroke:#bbb}} .chart .tick{{font-size:11px;fill:var(--muted)}}
.chart .dot{{fill:var(--accent);opacity:.35}} .chart .fit{{stroke:var(--ink);stroke-width:2}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:4px 0}} .legend i{{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:left}}
table.grid td,table.grid th{{text-align:center}} td.pick{{background:#fde7dc;font-weight:700}} td.pos{{color:#1f7a3a}} td.neg{{color:#b3261e}}
.wrap{{overflow-x:auto}} ul{{padding-left:20px}} li{{margin:4px 0}} code{{background:var(--soft);padding:1px 5px;border-radius:4px}}
.note{{color:var(--muted);font-size:13px}}
.method{{border-left:4px solid var(--accent);background:#fdf3ee;padding:10px 14px;border-radius:0 6px 6px 0;margin:16px 0}} .method ul{{margin:6px 0 0}} .method li{{font-size:14px}}
</style></head><body><main>
<div class="eyebrow">Natural gas data pipeline and research dashboard &middot; Amber Foster</div>
<h1>Does the weekly storage surprise move gas prices?</h1>
<p class="lead">Every Thursday at 10:30 ET the EIA reports how much natural gas went into or out of U.S. storage. This pipeline pulls the storage and futures data, measures how far each report lands from normal for that time of year, turns that surprise into a trading signal on NYMEX natural gas futures, and tests it with trading costs, risk limits, roll-safe pricing, and a test period the model never saw while it was being tuned.</p>
{banner}
<div class="method"><b>Methodology at a glance</b>
<ul>
<li><b>Signal:</b> storage change minus the seasonal norm (previous 5 years, same week plus or minus 2), divided by that season's usual variation (a z-score).</li>
<li><b>Roll-safe:</b> every trade is priced on one contract, NG2 at entry if the front month expires mid-trade, so monthly roll jumps never count as profit or loss.</li>
<li><b>No look-ahead:</b> entry at the release-day close, settings chosen on {html.escape(ctx['train_span'])} only, then scored once on {html.escape(ctx['test_span'])}.</li>
<li><b>Realistic:</b> {ctx['cost_bps']} bps costs each way, volatility-based sizing, a {ctx['max_leverage']}x cap, and a 500-run random baseline.</li>
</ul></div>

<h2>Result on the test period ({html.escape(ctx['test_span'])})</h2>
{_stat_cards(ctx['test_stats'], 'test')}
<p>Settings chosen on the training period only: trade when the surprise is at least <b>{ctx['threshold']}</b> times its typical size, hold for <b>{ctx['hold_days']}</b> trading days, cost <b>{ctx['cost_bps']} bps</b> each way. Against {ctx['baseline_runs']} random-direction runs with the same trades and costs, the strategy beat <b>{pct_beat:.0f}%</b> of them.</p>

<h2>Equity curve</h2>
{equity_svg}
<p class="note">Gray is the training period, where the settings were picked. Orange is the test period, which is the honest result.</p>

<h2>Does the surprise predict the move?</h2>
{scatter_svg}
<p class="note">Each dot is one report: the storage surprise (left = less gas than normal) against the price change over the next {ctx['hold_days']} trading days after release. A downward-sloping line means less gas than expected is followed by higher prices.</p>

<h2>How fast does the market price it in?</h2>
{decay_svg}
<p class="note">Average move in the direction the surprise pointed, measured from the release-day close. Bars that keep growing mean the market is slow to price in the report; bars that flatten or fade mean the move is mostly over by then.</p>

<h2>Training period ({html.escape(ctx['train_span'])})</h2>
{_stat_cards(ctx['train_stats'], 'training')}
<h3 style="font-size:15px;margin:16px 0 6px">Sharpe ratio for each setting tried</h3>
<div class="wrap">{grid_html}</div>
<p class="note">Highlighted cell is the setting carried into the test. If only one cell looks good, the result is probably luck; a broad area of good cells is more believable.</p>

<h2>Risk controls</h2>
<ul>
<li><b>Volatility targeting:</b> each position is sized so it aims for {int(ctx['vol_target']*100)}% annual volatility, using the last 20 days of price moves.</li>
<li><b>Leverage cap:</b> no position larger than {ctx['max_leverage']}x, even when markets are calm.</li>
<li><b>One position at a time:</b> a new signal is skipped if the last trade is still open.</li>
<li><b>Costs:</b> {ctx['cost_bps']} bps charged on entry and on exit.</li>
</ul>

<h2>How I kept the test honest</h2>
<ul>
<li><b>No look-ahead:</b> the "normal" change for each week uses only the 5 years before it. Entry is at the close on release day, so the report-day move is not counted.</li>
<li><b>Seasonal scaling:</b> each surprise is divided by how much storage changes usually vary at that time of year (same calendar week plus or minus 2 weeks, previous 5 years), so a summer miss and a winter miss are judged on the same scale.</li>
<li><b>Roll-safe prices:</b> the front-month futures series jumps every month when one contract expires and the next takes over. Every trade is priced on a single contract from entry to exit (contract 2 at entry when the front month expires mid-trade), so those jumps never count as profit or loss.</li>
<li><b>Out-of-sample test:</b> settings were picked on data up to {html.escape(ctx['split'])}; everything after is scored once.</li>
<li><b>Luck check:</b> compared with random trade directions using the same timing and costs.</li>
<li><b>Known limits:</b> the expectation is a 5-year seasonal average, not the analyst survey traders actually use, so real surprises are sharper. Daily closes miss the intraday reaction at 10:30 ET. The roll calendar ignores exchange holidays, so a roll can be off by a day near a holiday.</li>
<li><b>Data window:</b> EIA's free futures files stop on {html.escape(ctx.get('futures_end', ''))}, so the test runs through that date. Extending it needs a newer futures data source.</li>
</ul>

{ctx.get('paper_html', '')}
<h2>Next steps</h2>
<ul>
<li><b>Weather:</b> add heating and cooling degree day forecasts (HDD/CDD). Weather forecast revisions drive more gas volatility than anything else, and they shape what the market expects before each report.</li>
<li><b>A sharper expectation:</b> replace the 5-year seasonal average with the analyst consensus survey, so the surprise matches what traders actually react to.</li>
<li><b>Intraday timing:</b> use minute data to measure the reaction right at 10:30 ET instead of at the daily close.</li>
<li><b>Regional basis:</b> test whether surprises in specific regions move the spread between Henry Hub and hubs like Waha or Algonquin.</li>
</ul>

<h2>Most recent trades</h2>
<div class="wrap">{trades_html}</div>

<p class="note" style="margin-top:28px">Data: U.S. Energy Information Administration, weekly working gas in storage (Lower 48) and NYMEX natural gas futures contracts 1 and 2 (EIA's futures files end {html.escape(ctx.get('futures_end', ''))}). Generated {date.today():%B %d, %Y}.</p>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)