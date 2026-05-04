import os
from dotenv import load_dotenv

load_dotenv()

# --- Alpaca API ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    raise EnvironmentError("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in .env file")

# --- Account ---
ACCOUNT_SIZE = 2500             # USD
MAX_RISK_PER_TRADE = 100        # $100 max per trade (4% of account)
MAX_PORTFOLIO_EXPOSURE = 0.25   # 25% of account = $625 max total invested
MAX_POSITIONS = 5               # Max concurrent stock positions

# --- SuperTrend Parameters ---
SUPERTREND_PERIOD = 10          # ATR period for SuperTrend
SUPERTREND_MULTIPLIER = 3.0     # ATR multiplier for SuperTrend bands

# --- Stop Loss / Exit ---
ATR_STOP_MULTIPLIER = 2.0       # Hard stop: 2x ATR below entry
TRAILING_STOP_PCT = 0.05        # 5% trailing stop below highest price
MAX_DRAWDOWN_PCT = 0.25         # Pause bot if account drops 25%

# --- Data ---
HISTORICAL_DAYS = 90            # Days of OHLCV data to fetch

# --- Watchlist ---
WATCHLIST = [
    # Tech Heavy Watchlist (from tradingextremes.com)
    "AAPL", "AMD", "AMZN", "BABA", "BIDU", "BKNG",
    "CMG", "DIA", "META", "FFIV", "GOOG", "IWM",
    "MSFT", "NFLX", "NVDA", "QQQ", "SPOT", "SPY",
    "TLT", "TSLA", "ZM",

    # S&P 500 Diversified Watchlist (from tradingextremes.com)
    "ADBE", "ADSK", "AMGN", "APD", "AVGO", "BA",
    "BIIB", "CAT", "CLX", "CME", "COST", "CRM",
    "DIS", "FDX", "FTNT", "GD", "GOOGL", "GS",
    "HCA", "HD", "HON", "IBM", "JNJ", "JPM",
    "LLY", "LRCX", "MA", "MCD", "MMM", "NEE",
    "NOW", "PEP", "PG", "PYPL", "TGT", "TXN",
    "UNH", "UPS", "V", "VRTX", "WHR", "WMT",
]
# Excluded: VIX (index), RUT (index), BRK/B (slash in symbol)

# --- Schedule ---
SCAN_TIME = "16:05"             # Run daily at 4:05 PM ET (after market close)
