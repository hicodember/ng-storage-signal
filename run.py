"""Run the whole pipeline: load data, build the signal, tune, test, write the dashboard.

    python run.py            real EIA data (downloads it the first time)
    python run.py --refresh  download fresh data from the EIA
    python run.py --demo     simulated data, only for testing the code
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
from data import load_all, make_demo_data
from report import write_report
from signal_model import build_signal_table

THRESHOLDS = [0.5, 0.75, 1.0, 1.25, 1.5]
HOLDS = [1, 2, 3, 5, 10]


def fmt_ret(r):
    return f"{r['return'] * 100:+.2f}%" if "return" in r else ""


def paper_section(path):
    if not path.exists():
        return ""
    state = json.loads(path.read_text())
    reps = state["reports"][::-1]
    closed = [r for r in reps if r["status"] == "closed"]
    total = sum(r["return"] for r in closed) * 100
    rows = "".join(
        f"<tr><td>{r['report_day']}</td><td>{r['surprise_z']}</td><td>{r['signal']}</td>"
        f"<td>{r.get('legs', '')}</td><td>{r['status']}</td>"
        f"<td>{fmt_ret(r)}</td></tr>"
        for r in reps)
    return (f"<h2>Live paper trading (since {state['started']})</h2>"
            f"<p>{len(reps)} reports tracked, {len(closed)} closed trades, total {total:+.2f}%. "
            "Settings are frozen from the training period and never re-tuned.</p>"
            "<div class='wrap'><table><tr><th>Report</th><th>Surprise (z)</th><th>Signal</th>"
            f"<th>Legs</th><th>Status</th><th>Return</th></tr>{rows}</table></div>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use simulated data")
    ap.add_argument("--refresh", action="store_true", help="re-download EIA data")
    ap.add_argument("--split", default="2019-01-01", help="first date of the test period")
    ap.add_argument("--cost-bps", type=float, default=5.0, help="cost per side in basis points")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    storage, futures = make_demo_data() if args.demo else load_all(args.refresh)
    print(f"Storage weeks: {len(storage)}  ({storage.index[0].date()} to {storage.index[-1].date()})")
    print(f"Futures days:  {len(futures)}  ({futures.index[0].date()} to {futures.index[-1].date()})")

    signals = build_signal_table(storage)
    signals = signals[signals["report_date"] >= futures.index[0] + pd.Timedelta(days=40)]
    # only keep reports that have futures prices after them (EIA futures files end in April 2024)
    last_price = futures.index[-1]
    dropped = int((signals["report_date"] > last_price).sum())
    signals = signals[signals["report_date"] <= last_price]
    if dropped:
        print(f"Note: futures data ends {last_price.date()}, so {dropped} later storage reports are not tested")
    market = bt.Market(futures)

    split = pd.Timestamp(args.split)
    # leave a gap before the split so no training trade can exit inside the test period
    train = signals[signals["report_date"] < split - pd.Timedelta(days=21)]
    test = signals[signals["report_date"] >= split]

    grid, threshold, hold = bt.tune_in_sample(train, market, THRESHOLDS, HOLDS, args.cost_bps)
    print(f"Chosen on training data only: threshold {threshold}, hold {hold} days")

    def years(df):
        return (df["report_date"].iloc[-1] - df["report_date"].iloc[0]).days / 365.25

    train_trades = bt.trade_list(train, market, threshold, hold, args.cost_bps)
    test_trades = bt.trade_list(test, market, threshold, hold, args.cost_bps)
    # a trade that starts in training but would exit in the test period is dropped from training
    if not train_trades.empty:
        train_trades = train_trades[pd.to_datetime(train_trades["exit"]) < split]
    train_stats = bt.stats(train_trades, years(train))
    test_stats = bt.stats(test_trades, years(test))

    baseline = bt.random_baseline(test_trades, args.cost_bps)
    pct_beat = float((baseline < test_stats.get("total_return", np.nan)).mean() * 100) if len(baseline) else float("nan")

    decay_train = bt.signal_decay(train, market, threshold)
    decay_test = bt.signal_decay(test, market, threshold)
    reaction = bt.reaction_table(test, market, hold)

    for label, s in [("TRAIN", train_stats), ("TEST", test_stats)]:
        print(label, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()})
    print(f"Test beat {pct_beat:.0f}% of random-direction runs")

    here = Path(__file__).parent
    if not args.demo:  # paper_trade.py reuses these, so they are never re-tuned on new data
        (here / "settings.json").write_text(json.dumps({
            "threshold": threshold, "hold_days": hold, "cost_bps": args.cost_bps,
            "vol_target": 0.20, "max_leverage": 2.0, "chosen_on": f"reports before {split.date()}"}, indent=2))

    out = here / args.out
    write_report(out, {
        "demo": args.demo,
        "train_trades": train_trades, "test_trades": test_trades,
        "train_stats": train_stats, "test_stats": test_stats,
        "grid": grid, "threshold": threshold, "hold_days": hold,
        "cost_bps": args.cost_bps, "vol_target": 0.20, "max_leverage": 2.0,
        "baseline_pct": pct_beat, "baseline_runs": len(baseline),
        "decay_train": decay_train, "decay_test": decay_test,
        "reaction": reaction,
        "futures_end": f"{last_price:%B %d, %Y}",
        "paper_html": paper_section(here / "paper_trades.json"),
        "split": split.strftime("%B %Y"),
        "train_span": f"{train['report_date'].iloc[0]:%b %Y} to {split - pd.Timedelta(days=1):%b %Y}",
        "test_span": f"{split:%b %Y} to {test['report_date'].iloc[-1]:%b %Y}",
    })
    print(f"Dashboard written to {out}")


if __name__ == "__main__":
    main()