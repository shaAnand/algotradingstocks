import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

from dataclasses import dataclass, field
from typing import Optional

from data.stock_fetcher import get_stock_bars
from indicators.supertrend import calculate_supertrend, is_bullish_flip, is_bullish, get_supertrend_level
from indicators.atr import get_atr, get_atr_stop_price


@dataclass
class SignalResult:
    symbol: str
    signal: str = "NO_SIGNAL"      # BUY | NO_SIGNAL | ERROR
    latest_price: float = 0.0
    supertrend_level: float = 0.0  # Current SuperTrend line (trailing stop reference)
    atr: float = 0.0               # Current ATR value
    atr_stop: float = 0.0          # Hard stop price if entered now (entry - 2xATR)
    st_direction: int = 0          # 1 = bullish, -1 = bearish
    is_flip: bool = False          # True if today is the flip candle
    reasons: list = field(default_factory=list)


def analyze(symbol: str) -> SignalResult:
    """
    Analyzes a symbol using the SuperTrend strategy.

    BUY signal conditions:
      1. SuperTrend just flipped from bearish (-1) to bullish (1) on today's bar
      2. This is the entry candle — act on the flip itself

    NO_SIGNAL conditions:
      - SuperTrend is already bullish (no fresh flip — position would have been entered earlier)
      - SuperTrend is bearish (do not enter long)

    Returns a SignalResult with full context for logging and position sizing.
    """
    result = SignalResult(symbol=symbol)

    try:
        df = get_stock_bars(symbol)

        if len(df) < 20:
            result.signal = "ERROR"
            result.reasons.append(f"Insufficient data: {len(df)} bars")
            return result

        df = calculate_supertrend(df)

        latest = df.iloc[-1]
        result.latest_price = float(latest["close"])
        result.supertrend_level = get_supertrend_level(df)
        result.atr = get_atr(df)
        result.atr_stop = get_atr_stop_price(result.latest_price, df)
        result.st_direction = int(latest["st_direction"])
        result.is_flip = is_bullish_flip(df)

        if result.is_flip:
            result.signal = "BUY"
            result.reasons.append("SuperTrend flipped bullish today")
            result.reasons.append(f"SuperTrend line: ${result.supertrend_level:.2f}")
            result.reasons.append(f"ATR stop if entered: ${result.atr_stop:.2f}")
        elif is_bullish(df):
            result.signal = "NO_SIGNAL"
            result.reasons.append("SuperTrend bullish but no fresh flip (already in uptrend)")
        else:
            result.signal = "NO_SIGNAL"
            result.reasons.append("SuperTrend bearish — no long entry")

    except Exception as e:
        result.signal = "ERROR"
        result.reasons.append(str(e))

    return result


if __name__ == "__main__":
    for symbol in ["AAPL", "NVDA", "TSLA"]:
        r = analyze(symbol)
        print(f"\n{symbol}: {r.signal}")
        print(f"  Price:     ${r.latest_price:.2f}")
        print(f"  ST Level:  ${r.supertrend_level:.2f}  (dir: {'+' if r.st_direction == 1 else '-'})")
        print(f"  ATR:       ${r.atr:.2f}")
        print(f"  ATR Stop:  ${r.atr_stop:.2f}")
        print(f"  Flip:      {r.is_flip}")
        for reason in r.reasons:
            print(f"  → {reason}")
