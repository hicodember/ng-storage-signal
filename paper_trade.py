"""Forward paper trading: record each new storage report's signal, with no real money.

Run once a week after the Thursday report (Friday is safest, because the free EIA
price files post a day or so late):

    python paper_trade.py

What it does:
  1. Downloads fresh EIA data.
  2. Uses the settings that run.py chose on the TRAINING period (settings.json).
     They are never re-tuned on new data.
  3. For each report since tracking began that is not logged yet, records the
     signal. If it trades, entry is the release-day close and exit is the close
     `hold_days` later, priced on one contract (roll-safe), with the same costs.
  4. Fills in results for open trades once their exit price is available.
Everything is saved in paper_trades.json, and run.py shows it on the dashboard.
"""
import json
from pathlib import Path

import pandas as pd

import backtest as bt
from data import load_all
from rolls import front_delivery_month
from signal_model import build_signal_table, signal_direction

HERE = Path(__file__).parent
STATE = HERE / "paper_trades.json"
SETTINGS = HERE / "settings.json"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"started": pd.Timestamp.today().strftime("%Y-%m-%d"), "reports": []}


def main():
    if not SETTINGS.exists():
        raise SystemExit("Run `python run.py` first so the training settings are saved.")
    cfg = json.loads(SETTINGS.read_text())
    state = load_state()
    started = pd.Timestamp(state["started"])

    storage, futures = load_all(refresh=True)
    stale = (pd.Timestamp.today() - futures.index[-1]).days
    if stale > 10:
        print(f"Warning: the latest futures price is from {futures.index[-1].date()} ({stale} days old).")
        print("EIA's free futures files stopped updating, so new reports can be logged but not priced.")
    signals = build_signal_table(storage)
    market = bt.Market(futures)
    direction = signal_direction(signals["surprise_z"], cfg["threshold"])
    logged = {r["week_ending"] for r in state["reports"]}

    for week_end, row in signals[signals["report_date"] >= started].iterrows():
        key = week_end.strftime("%Y-%m-%d")
        if key in logged:
            continue
        d = int(direction.loc[week_end])
        state["reports"].append({
            "week_ending": key,
            "report_day": row["report_date"].strftime("%Y-%m-%d"),
            "surprise_z": round(float(row["surprise_z"]), 2),
            "signal": {1: "long", -1: "short", 0: "no trade"}[d],
            "status": "open" if d else "no trade",
        })

    n = len(market.futures)
    for r in state["reports"]:
        if r["status"] != "open":
            continue
        i = market.entry_index(pd.Timestamp(r["report_day"]))
        if i >= n or market.futures.index[i] != pd.Timestamp(r["report_day"]):
            continue  # report-day price not posted yet
        v = market.vol.iloc[i]
        r["entry"] = market.futures.index[i].strftime("%Y-%m-%d")
        r["size"] = round(float(min(cfg["vol_target"] / v, cfg["max_leverage"])), 2)
        if i + cfg["hold_days"] < n:
            d = 1 if r["signal"] == "long" else -1
            gross = d * market.ret(i, i + cfg["hold_days"])
            exit_day = market.futures.index[i + cfg["hold_days"]]
            r["exit"] = exit_day.strftime("%Y-%m-%d")
            rolled = front_delivery_month(exit_day) != front_delivery_month(market.futures.index[i])
            r["legs"] = "NG2 in, NG1 out" if rolled else "NG1 in, NG1 out"
            r["return"] = round(r["size"] * (gross - 2 * cfg["cost_bps"] / 1e4), 5)
            r["status"] = "closed"

    STATE.write_text(json.dumps(state, indent=2))
    closed = [r for r in state["reports"] if r["status"] == "closed"]
    print(f"Paper trading since {state['started']}: {len(state['reports'])} reports, "
          f"{len(closed)} closed trades, total {sum(r['return'] for r in closed) * 100:+.2f}%")
    print("Run `python run.py` to refresh the dashboard.")


if __name__ == "__main__":
    main()