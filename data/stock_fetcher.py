import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
import pandas as pd

from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, HISTORICAL_DAYS

_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

ET = ZoneInfo("America/New_York")


def get_stock_bars(symbol: str, days: int = HISTORICAL_DAYS) -> pd.DataFrame:
    """
    Fetch daily OHLCV bars for a symbol.

    Returns a DataFrame with columns: open, high, low, close, volume
    Index is a DatetimeIndex in ET timezone.
    Raises RuntimeError if data cannot be fetched.
    """
    end = datetime.now(ET)
    start = end - timedelta(days=days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )

    try:
        bars = _client.get_stock_bars(request)
        df = bars.df

        if df.empty:
            raise RuntimeError(f"No data returned for {symbol}")

        # If multi-index (symbol, timestamp), drop symbol level
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        df.index = pd.DatetimeIndex(df.index).tz_convert(ET)
        df = df[["open", "high", "low", "close", "volume"]].sort_index()
        return df

    except Exception as e:
        raise RuntimeError(f"Failed to fetch bars for {symbol}: {e}")


def get_latest_price(symbol: str) -> float:
    """
    Returns the most recent closing price for a symbol.
    """
    df = get_stock_bars(symbol, days=5)
    return float(df["close"].iloc[-1])


if __name__ == "__main__":
    symbol = "AAPL"
    print(f"Fetching {symbol} data...")
    df = get_stock_bars(symbol)
    print(f"Rows returned: {len(df)}")
    print(df.tail(3))
    print(f"\nLatest price: ${get_latest_price(symbol):.2f}")
