import pandas as pd
import numpy as np
from config.settings import SUPERTREND_PERIOD, SUPERTREND_MULTIPLIER


def calculate_atr(df: pd.DataFrame, period: int = SUPERTREND_PERIOD) -> pd.Series:
    """
    Calculates Average True Range (ATR) using simple rolling mean.

    True Range = max of:
      - high - low
      - abs(high - prev_close)
      - abs(low - prev_close)
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

    return tr.rolling(period).mean()


def calculate_supertrend(
    df: pd.DataFrame,
    period: int = SUPERTREND_PERIOD,
    multiplier: float = SUPERTREND_MULTIPLIER,
) -> pd.DataFrame:
    """
    Calculates SuperTrend indicator and adds columns to a copy of df.

    Columns added:
        atr             - Average True Range
        st_upper_band   - Upper band = midpoint + (multiplier * ATR)
        st_lower_band   - Lower band = midpoint - (multiplier * ATR)
        supertrend      - The active SuperTrend line (trailing stop level)
        st_direction    - 1 = bullish (price above supertrend), -1 = bearish

    Algorithm:
      - midpoint = (high + low) / 2
      - basic_upper = midpoint + multiplier * ATR
      - basic_lower = midpoint - multiplier * ATR
      - Final bands are adjusted: upper can only decrease, lower can only increase
        (unless price crosses through them, which resets direction)
    """
    df = df.copy()
    atr = calculate_atr(df, period)
    df["atr"] = atr

    hl2 = (df["high"] + df["low"]) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(df)
    upper_band = basic_upper.copy()
    lower_band = basic_lower.copy()
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    close = df["close"].values
    upper_vals = upper_band.values.copy()
    lower_vals = lower_band.values.copy()
    basic_upper_vals = basic_upper.values
    basic_lower_vals = basic_lower.values
    st_vals = np.full(n, np.nan)
    dir_vals = np.full(n, 1, dtype=int)

    # Find first bar where ATR is valid (after warmup period)
    first_valid = None
    for i in range(n):
        if not np.isnan(basic_upper_vals[i]) and not np.isnan(basic_lower_vals[i]):
            first_valid = i
            break

    if first_valid is None:
        # Not enough data for any calculation
        df["st_upper_band"] = upper_vals
        df["st_lower_band"] = lower_vals
        df["supertrend"] = st_vals
        df["st_direction"] = dir_vals
        return df

    # Initialize first valid bar
    upper_vals[first_valid] = basic_upper_vals[first_valid]
    lower_vals[first_valid] = basic_lower_vals[first_valid]
    dir_vals[first_valid] = 1  # Assume bullish to start
    st_vals[first_valid] = lower_vals[first_valid]

    for i in range(first_valid + 1, n):
        if np.isnan(basic_upper_vals[i]) or np.isnan(basic_lower_vals[i]):
            continue

        # Upper band: only tighten (decrease) unless price closes above previous upper
        if basic_upper_vals[i] < upper_vals[i - 1] or close[i - 1] > upper_vals[i - 1]:
            upper_vals[i] = basic_upper_vals[i]
        else:
            upper_vals[i] = upper_vals[i - 1]

        # Lower band: only tighten (increase) unless price closes below previous lower
        if basic_lower_vals[i] > lower_vals[i - 1] or close[i - 1] < lower_vals[i - 1]:
            lower_vals[i] = basic_lower_vals[i]
        else:
            lower_vals[i] = lower_vals[i - 1]

        # Determine direction
        prev_dir = dir_vals[i - 1]

        if prev_dir == -1:
            # Was bearish: flip bullish if price closes above upper band
            if close[i] > upper_vals[i]:
                dir_vals[i] = 1
            else:
                dir_vals[i] = -1
        else:
            # Was bullish: flip bearish if price closes below lower band
            if close[i] < lower_vals[i]:
                dir_vals[i] = -1
            else:
                dir_vals[i] = 1

        # SuperTrend line = lower band when bullish, upper band when bearish
        st_vals[i] = lower_vals[i] if dir_vals[i] == 1 else upper_vals[i]

    df["st_upper_band"] = upper_vals
    df["st_lower_band"] = lower_vals
    df["supertrend"] = st_vals
    df["st_direction"] = dir_vals

    return df


def is_bullish_flip(df: pd.DataFrame) -> bool:
    """
    Returns True if SuperTrend just flipped from bearish to bullish on the latest bar.

    A flip means: yesterday direction was -1 (bearish), today direction is 1 (bullish).
    This is the primary BUY signal.
    """
    if len(df) < 2:
        return False
    if "st_direction" not in df.columns:
        df = calculate_supertrend(df)
    prev = df["st_direction"].iloc[-2]
    curr = df["st_direction"].iloc[-1]
    return int(prev) == -1 and int(curr) == 1


def is_bullish(df: pd.DataFrame) -> bool:
    """
    Returns True if SuperTrend is currently bullish (direction == 1).
    Used to confirm existing positions are still valid.
    """
    if "st_direction" not in df.columns:
        df = calculate_supertrend(df)
    return int(df["st_direction"].iloc[-1]) == 1


def get_supertrend_level(df: pd.DataFrame) -> float:
    """
    Returns the current SuperTrend level (the trailing stop line from ST).
    """
    if "supertrend" not in df.columns:
        df = calculate_supertrend(df)
    return float(df["supertrend"].iloc[-1])


if __name__ == "__main__":
    # Quick smoke test using AAPL data
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from data.stock_fetcher import get_stock_bars
    df = get_stock_bars("AAPL")
    result = calculate_supertrend(df)
    print(result[["close", "atr", "st_lower_band", "st_upper_band", "supertrend", "st_direction"]].tail(10))
    print(f"\nBullish flip today: {is_bullish_flip(result)}")
    print(f"Currently bullish:  {is_bullish(result)}")
    print(f"SuperTrend level:   ${get_supertrend_level(result):.2f}")
