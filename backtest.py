"""Event-driven backtest with costs, risk limits, and an honest out-of-sample split.

Timing (no look-ahead): the report comes out Thursday at 10:30 ET. With daily
closing prices we enter at that day's close and exit at the close `hold_days`
trading days later. The report-day move itself is NOT counted, because we could
not have traded before the release. Every trade is priced on a single futures
contract, so monthly roll jumps never show up as profit or loss (see rolls.py).
"""
import numpy as np
import pandas as pd

from rolls import clean_daily_returns, front_delivery_month, same_contract_return
from signal_model import signal_direction


def _month_label(m):
    return pd.Timestamp(year=m // 12, month=m % 12 + 1, day=1).strftime("%b %Y")


class Market:
    """Futures prices plus precomputed roll-safe daily returns and volatility."""

    def __init__(self, futures: pd.DataFrame):
        self.futures = futures.sort_index()
        self.daily = clean_daily_returns(self.futures)
        self.vol = (self.daily.rolling(20).std() * np.sqrt(252)).reindex(self.futures.index)

    def entry_index(self, report_day):
        return self.futures.index.searchsorted(report_day)  # first trading day on or after release

    def ret(self, i_entry, i_exit):
        return same_contract_return(self.futures, i_entry, i_exit)


def trade_list(signals, market, threshold, hold_days, cost_bps, vol_target=0.20, max_leverage=2.0):
    direction = signal_direction(signals["surprise_z"], threshold)
    n = len(market.futures)
    rows, last_exit = [], None
    for week_end, d in direction.items():
        if d == 0:
            continue
        report_day = signals.loc[week_end, "report_date"]
        i = market.entry_index(report_day)
        if i + hold_days >= n:
            continue
        entry_day, exit_day = market.futures.index[i], market.futures.index[i + hold_days]
        if last_exit is not None and entry_day <= last_exit:
            continue  # one position at a time
        v = market.vol.iloc[i]
        if not np.isfinite(v) or v <= 0:
            continue
        size = min(vol_target / v, max_leverage)  # volatility targeting with a hard cap
        gross = d * market.ret(i, i + hold_days)
        m_entry, m_exit = front_delivery_month(entry_day), front_delivery_month(exit_day)
        rolled = m_exit != m_entry
        cost = 2 * cost_bps / 1e4  # in and out
        rows.append({
            "week_ending": week_end.date(), "report_day": report_day.date(),
            "entry": entry_day.date(), "exit": exit_day.date(),
            "direction": "long" if d > 0 else "short",
            "contract": _month_label(m_exit),
            "legs": "NG2 in, NG1 out" if rolled else "NG1 in, NG1 out",
            "surprise_z": round(float(signals.loc[week_end, "surprise_z"]), 2),
            "size": round(float(size), 2),
            "gross": gross,
            "return": size * (gross - cost),
        })
        last_exit = exit_day
    return pd.DataFrame(rows)


def stats(trades: pd.DataFrame, years: float) -> dict:
    if trades.empty:
        return {"trades": 0}
    r = trades["return"]
    equity = (1 + r).cumprod()
    drawdown = equity / equity.cummax() - 1
    per_year = len(r) / max(years, 1e-9)
    sd = r.std(ddof=1) if len(r) > 1 else np.nan
    return {
        "trades": int(len(r)),
        "hit_rate": float((r > 0).mean()),
        "avg_trade": float(r.mean()),
        "total_return": float(equity.iloc[-1] - 1),
        "sharpe": float(r.mean() / sd * np.sqrt(per_year)) if sd and sd > 0 else np.nan,
        "max_drawdown": float(drawdown.min()),
        "t_stat": float(r.mean() / (sd / np.sqrt(len(r)))) if sd and sd > 0 else np.nan,
    }


def random_baseline(trades: pd.DataFrame, cost_bps: float, runs=500, seed=1):
    """Same trades, same sizes and costs, random direction. Shows what luck alone looks like."""
    if trades.empty:
        return np.array([])
    rng = np.random.default_rng(seed)
    sign = np.where(trades["direction"] == "long", 1, -1)
    raw = sign * trades["gross"].to_numpy()  # undirected price move of each trade
    cost = 2 * cost_bps / 1e4
    totals = []
    for _ in range(runs):
        flip = rng.choice([-1, 1], size=len(trades))
        r = trades["size"].to_numpy() * (flip * raw - cost)
        totals.append(np.prod(1 + r) - 1)
    return np.array(totals)


def tune_in_sample(signals, market, thresholds, holds, cost_bps):
    """Pick settings using ONLY the training period. The test period is never seen here."""
    years = (signals.index[-1] - signals.index[0]).days / 365.25
    grid = []
    for th in thresholds:
        for h in holds:
            s = stats(trade_list(signals, market, th, h, cost_bps), years)
            grid.append({"threshold": th, "hold_days": h, **s})
    grid = pd.DataFrame(grid)
    ok = grid[grid["trades"] >= 20]
    best = ok.sort_values("sharpe", ascending=False).iloc[0]
    return grid, float(best["threshold"]), int(best["hold_days"])


def signal_decay(signals, market, threshold, max_days=10):
    """Average signed move 1..max_days after release for every report past the threshold.

    Positive means prices kept moving the way the surprise pointed. Where the bars
    flatten out is roughly when the market has finished pricing in the report.
    """
    direction = signal_direction(signals["surprise_z"], threshold)
    n = len(market.futures)
    out = {h: [] for h in range(1, max_days + 1)}
    for week_end, d in direction.items():
        if d == 0:
            continue
        i = market.entry_index(signals.loc[week_end, "report_date"])
        for h in out:
            if i + h < n:
                out[h].append(d * market.ret(i, i + h))
    return pd.Series({h: np.mean(v) if v else np.nan for h, v in out.items()})


def reaction_table(signals, market, hold_days):
    """Surprise z against the same-contract move over the next hold_days, for every report."""
    rows = []
    n = len(market.futures)
    for week_end, row in signals.iterrows():
        i = market.entry_index(row["report_date"])
        if i + hold_days < n:
            rows.append({"surprise_z": row["surprise_z"], "next_return": market.ret(i, i + hold_days)})
    return pd.DataFrame(rows)
