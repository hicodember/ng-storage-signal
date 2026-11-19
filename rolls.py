"""Futures roll handling.

NYMEX Henry Hub natural gas futures stop trading three business days before the
first calendar day of the delivery month. EIA's "contract 1" series always shows
whichever contract is closest to expiring, so on the day after expiration it
switches to the next month's contract. That switch is a fake price jump, not a
market move, and a naive backtest would trade it.

Fix used here: every trade is priced on ONE contract from entry to exit.
  - If the front month does not expire during the trade: contract 1 at entry and exit.
  - If it does: the contract that is contract 1 at exit was contract 2 at entry, so
    use contract 2 at entry and contract 1 at exit.
Holidays are not modeled in the expiration calendar, so a roll date can be off by
a day around holidays. Trades are at most a couple of weeks, so at most one roll
can fall inside a trade.
"""
import pandas as pd


def last_trade_date(year: int, month: int) -> pd.Timestamp:
    """Three business days before the first calendar day of the delivery month."""
    first = pd.Timestamp(year=year, month=month, day=1)
    return first - pd.offsets.BDay(3)


def front_delivery_month(day) -> int:
    """Delivery month of the front contract on `day`, as a month count (year*12 + month-1)."""
    day = pd.Timestamp(day).normalize()
    y, m = day.year, day.month + 1  # the contract trading in month M usually delivers in M+1
    if m > 12:
        y, m = y + 1, 1
    if day > last_trade_date(y, m):  # that contract already expired, so the front is one later
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return y * 12 + (m - 1)


def same_contract_return(futures: pd.DataFrame, i_entry: int, i_exit: int) -> float:
    """Return from entry to exit on a single contract (no fake roll jumps)."""
    entry_day, exit_day = futures.index[i_entry], futures.index[i_exit]
    rolled = front_delivery_month(exit_day) != front_delivery_month(entry_day)
    entry_price = futures["c2"].iloc[i_entry] if rolled else futures["c1"].iloc[i_entry]
    return futures["c1"].iloc[i_exit] / entry_price - 1


def clean_daily_returns(futures: pd.DataFrame) -> pd.Series:
    """Daily contract-1 returns with roll days computed on the same contract."""
    out = []
    for i in range(1, len(futures)):
        out.append(same_contract_return(futures, i - 1, i))
    return pd.Series(out, index=futures.index[1:])
