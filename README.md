# Natural Gas Storage Signal

A data pipeline and research dashboard that asks one question: **does the weekly EIA natural gas storage surprise predict how gas futures move afterward?**

Every Thursday at 10:30 ET the U.S. Energy Information Administration reports how much natural gas went into or out of storage. Traders compare it with what they expected. This project pulls that data, measures how surprising each report was for its time of year, turns the surprise into a trading signal on NYMEX natural gas futures, and tests it the way a trading desk would: with costs, risk limits, roll-safe pricing, and a test period the model never saw while it was being tuned.

## Hypothesis

Less gas in storage than normal for the season means a tighter market, so prices should rise after the report. More gas than normal should push prices down.

## How it works

| Step | File | What it does |
|---|---|---|
| 1. Data | `data.py` | Downloads three free EIA series: weekly Lower 48 storage, and daily futures contracts 1 and 2. Caches them in `data/`. |
| 2. Signal | `signal_model.py` | Expected change = average change for the same calendar week (plus or minus 2 weeks) over the previous 5 years. Surprise z-score = (actual minus expected) divided by the standard deviation of those seasonal changes. |
| 3. Rolls | `rolls.py` | Rebuilds the NYMEX expiration calendar (3 business days before the delivery month) and prices every trade on one contract, so monthly roll jumps never count as profit or loss. |
| 4. Backtest | `backtest.py` | Enters at the release-day close, holds a fixed number of days, sizes by recent volatility (20% target, 2x cap), one position at a time, costs on both sides. |
| 5. Evaluation | `run.py` | Tunes the threshold and holding period on 2012 to 2018 only, scores the chosen setting once on 2019 to today, compares with 500 random-direction runs, and measures signal decay over 1 to 10 days. |
| 6. Dashboard | `report.py` | Writes `dashboard.html`, a single page that opens in any browser, including on a phone. |
| 7. Paper trading | `paper_trade.py` | Run weekly to log new signals going forward with the frozen settings, no real money. |

## Avoiding the usual backtest mistakes

- **Look-ahead bias:** the seasonal norm for each week uses only earlier data. Entry is at the close on release day, so the release-day move itself is never counted. A test that scrambles all post-2019 data leaves the training results unchanged.
- **Roll gaps:** EIA's contract 1 series switches contracts after each expiration. Trades that cross an expiration are priced on contract 2 at entry and contract 1 at exit, which is the same physical contract. Every trade logs which legs it used.
- **Overfitting:** settings are picked on the training period only, and the grid of all settings tried is shown so you can see whether the result is broad or a single lucky cell.
- **Luck:** the test result is ranked against 500 runs with the same trades and random directions.

## Known limits

- The expectation is a 5-year seasonal average, not the analyst survey traders actually use, so real surprises are sharper than this proxy.
- Daily closes miss the intraday reaction at 10:30 ET.
- The expiration calendar ignores exchange holidays, so a roll can be off by one day near a holiday.

## Next steps

- Heating and cooling degree day forecasts (HDD/CDD). Weather revisions are the biggest driver of gas volatility.
- The analyst consensus survey as the expectation.
- Minute data around the 10:30 ET release.
- Regional basis spreads, such as Henry Hub against Waha or Algonquin.

## Run it

Requires Python 3.10 or newer.

```
pip install -r requirements.txt
python run.py
```

The first run downloads the EIA data, which takes a minute. Open `dashboard.html` in a browser to see the results.

- `python run.py --refresh` downloads fresh data.
- `python run.py --demo` runs on simulated data to test the code. Those numbers are not real results.
- `python paper_trade.py` logs new reports going forward. Run it each Friday, then run `python run.py` again to update the dashboard.

If the download is blocked on your network, download these three files in a browser and put them in a `data` folder next to `run.py`, then run again:

- https://www.eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls
- https://www.eia.gov/dnav/ng/hist_xls/RNGC1d.xls
- https://www.eia.gov/dnav/ng/hist_xls/RNGC2d.xls

Data: U.S. Energy Information Administration.
