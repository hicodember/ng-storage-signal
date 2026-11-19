"""Load U.S. natural gas data from the EIA (Energy Information Administration).

Three public series:
  - Weekly Lower 48 working gas in underground storage (Bcf), week ending Friday.
  - Daily NYMEX natural gas futures, contract 1 (front month), $/MMBtu.
  - Daily NYMEX natural gas futures, contract 2 (next month), $/MMBtu.

Contract 2 is what lets the backtest price every trade on ONE contract from entry
to exit, even when the front month expires in between (see rolls.py).

Order of sources: a cached CSV in data/, then an .xls you downloaded yourself into
data/, then the EIA download link.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from rolls import front_delivery_month

DATA_DIR = Path(__file__).parent / "data"

SOURCES = {
    "storage": ("https://www.eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls",
                "Weekly Lower 48 working gas in storage (Bcf)"),
    "c1": ("https://www.eia.gov/dnav/ng/hist_xls/RNGC1d.xls",
           "NYMEX natural gas futures, contract 1"),
    "c2": ("https://www.eia.gov/dnav/ng/hist_xls/RNGC2d.xls",
           "NYMEX natural gas futures, contract 2"),
}


def _read_eia_xls(source):
    """EIA history files keep the data on sheet 'Data 1' under two header rows."""
    df = pd.read_excel(source, sheet_name="Data 1", skiprows=2)
    df = df.iloc[:, :2]
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().sort_values("date").set_index("date")["value"]


def load_series(key, refresh=False):
    DATA_DIR.mkdir(exist_ok=True)
    cache = DATA_DIR / f"{key}.csv"
    if cache.exists() and not refresh:
        s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0]
        s.name = key
        return s
    url, label = SOURCES[key]
    local_xls = DATA_DIR / Path(url).name
    source = local_xls if local_xls.exists() else url
    print(f"Loading {label} from {source}")
    s = _read_eia_xls(source)
    s.name = key
    s.to_csv(cache)
    return s


def load_all(refresh=False):
    storage = load_series("storage", refresh)
    futures = pd.concat([load_series("c1", refresh), load_series("c2", refresh)], axis=1).dropna()
    return storage, futures


def make_demo_data(seed=7):
    """Realistic fake data for testing the pipeline. Never present it as real results.

    Storage follows a seasonal injection/withdrawal cycle with noise that is larger
    in winter. Contract 1 and 2 follow the same random walk with a contango spread,
    so the front-month series jumps at every roll, just like the real one. Prices
    react a little to storage surprises so the pipeline has something to find.
    """
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2010-01-01", "2026-11-13", freq="W-FRI")
    woy = weeks.isocalendar().week.to_numpy().astype(float)
    normal_change = -95 * np.cos(2 * np.pi * (woy - 4) / 52)
    noise_sd = 12 + 10 * (np.cos(2 * np.pi * (woy - 4) / 52) > 0.3)  # winter is noisier
    noise = rng.normal(0, 1, len(weeks)) * noise_sd
    change = normal_change + noise
    storage = pd.Series(2500 + np.cumsum(change - change.mean()), index=weeks, name="storage")

    days = pd.bdate_range(weeks[0], weeks[-1] + pd.Timedelta(days=14))
    rets = rng.normal(0, 0.03, len(days))
    z = pd.Series(noise / noise_sd, index=weeks + pd.Timedelta(days=6))
    for d, zv in z.items():
        i = days.searchsorted(d)
        if i + 1 < len(days):
            rets[i + 1:i + 4] += -0.0015 * zv  # reaction spread over the next few days
    level = pd.Series(3.0 * np.exp(np.cumsum(rets) * 0.6), index=days)

    # each delivery month trades at its own premium to the common level, so the
    # front-month series jumps at every roll, like the real one
    month = pd.Series([front_delivery_month(d) for d in days], index=days)
    months = sorted(set(month) | {m + 1 for m in month})
    premium = {m: float(rng.uniform(0.94, 1.08)) for m in months}
    c1 = level * month.map(premium).to_numpy()
    c2 = level * month.map(lambda m: premium[m + 1]).to_numpy()
    futures = pd.DataFrame({"c1": c1, "c2": c2}, index=days)
    return storage, futures
