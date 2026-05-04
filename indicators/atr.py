import pandas as pd
from config.settings import SUPERTREND_PERIOD, ATR_STOP_MULTIPLIER


def get_atr(df: pd.DataFrame, period: int = SUPERTREND_PERIOD) -> float:
    """
    Returns the most recent ATR value.

    Uses simple rolling mean (SMA-based ATR), consistent with SuperTrend calculation.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_series = tr.rolling(period).mean()
    return float(atr_series.iloc[-1])


def get_atr_stop_price(entry_price: float, df: pd.DataFrame) -> float:
    """
    Calculates the hard stop-loss price using 2x ATR below entry.

    Formula: entry_price - (ATR_STOP_MULTIPLIER * ATR)

    This is the absolute floor — never adjust upward once set.
    Example: entry=$100, ATR=$3 → stop = $100 - (2 * $3) = $94
    """
    atr = get_atr(df)
    return round(entry_price - (ATR_STOP_MULTIPLIER * atr), 2)
