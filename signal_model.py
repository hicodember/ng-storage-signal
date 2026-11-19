"""Turn the weekly storage report into a trading signal.

The market reacts to the *surprise*: how much gas went into or out of storage
compared with what was expected. Real desks use an analyst survey as the
expectation, which is not free. This project uses a public, reproducible proxy
built only from data available before each report (no look-ahead):

  expected change = average change for the same time of year over the previous
                    5 years (that calendar week plus or minus 2 weeks)
  surprise z      = (actual change - expected change) / standard deviation of
                    those same seasonal changes

Dividing by the seasonal standard deviation matters: a 15 Bcf miss in a calm
summer week is a much bigger surprise than the same miss in a volatile winter week.
"""
import numpy as np
import pandas as pd

REPORT_LAG_DAYS = 6  # week ends Friday; EIA releases the following Thursday at 10:30 ET


def build_signal_table(storage: pd.Series, lookback_years: int = 5, window_weeks: int = 2) -> pd.DataFrame:
    df = pd.DataFrame({"storage": storage})
    df["change"] = df["storage"].diff()
    df["week"] = df.index.isocalendar().week.astype(int).clip(upper=52)
    df["report_date"] = df.index + pd.Timedelta(days=REPORT_LAG_DAYS)

    exp_mean, exp_sd = [], []
    for date, row in df.iterrows():
        past = df[(df.index < date) & (df.index >= date - pd.DateOffset(years=lookback_years))]
        dist = (past["week"] - row["week"]).abs()
        dist = np.minimum(dist, 52 - dist)  # week 52 and week 1 are neighbors
        seasonal = past.loc[dist <= window_weeks, "change"].dropna()
        if len(seasonal) >= 10:
            exp_mean.append(seasonal.mean())
            exp_sd.append(seasonal.std(ddof=1))
        else:
            exp_mean.append(np.nan)
            exp_sd.append(np.nan)
    df["expected_change"] = exp_mean
    df["seasonal_sd"] = exp_sd
    df["surprise"] = df["change"] - df["expected_change"]
    df["surprise_z"] = df["surprise"] / df["seasonal_sd"]
    return df.dropna(subset=["surprise_z"])


def signal_direction(surprise_z: pd.Series, threshold: float) -> pd.Series:
    """Less gas than normal (negative surprise) is bullish, so go long; more gas, go short."""
    direction = pd.Series(0, index=surprise_z.index)
    direction[surprise_z <= -threshold] = 1
    direction[surprise_z >= threshold] = -1
    return direction
