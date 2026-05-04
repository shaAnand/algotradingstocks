import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import math
from dataclasses import dataclass
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from config.settings import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER,
    ACCOUNT_SIZE, MAX_RISK_PER_TRADE, MAX_POSITIONS,
    MAX_PORTFOLIO_EXPOSURE, MAX_DRAWDOWN_PCT,
    TRAILING_STOP_PCT, ATR_STOP_MULTIPLIER,
)
from signals.generator import SignalResult

_trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)


@dataclass
class PositionSizing:
    symbol: str
    shares: int               # Number of shares to buy
    cost: float               # Total cost (shares * price)
    entry_price: float        # Price at entry
    atr_stop: float           # Hard stop: entry - 2xATR
    trailing_stop: float      # Initial trailing stop: entry * (1 - 5%)
    max_loss: float           # Max possible loss (entry - atr_stop) * shares
    valid: bool = True
    reason: str = ""


def calculate_position_size(signal: SignalResult) -> PositionSizing:
    """
    Calculates how many shares to buy given a BUY signal.

    Position sizing rules:
      1. Max $100 per trade (MAX_RISK_PER_TRADE)
      2. Buy as many whole shares as $100 allows
      3. If 1 share costs more than $100, skip the trade
      4. Calculate ATR stop and trailing stop prices

    Returns a PositionSizing with shares=0 and valid=False if the trade should be skipped.
    """
    price = signal.latest_price

    if price <= 0:
        return PositionSizing(
            symbol=signal.symbol, shares=0, cost=0,
            entry_price=price, atr_stop=0, trailing_stop=0, max_loss=0,
            valid=False, reason="Invalid price"
        )

    # How many shares can we buy within $100?
    shares = int(MAX_RISK_PER_TRADE / price)

    if shares < 1:
        return PositionSizing(
            symbol=signal.symbol, shares=0, cost=0,
            entry_price=price, atr_stop=signal.atr_stop, trailing_stop=0, max_loss=0,
            valid=False,
            reason=f"Price ${price:.2f} exceeds max trade size ${MAX_RISK_PER_TRADE}"
        )

    cost = round(shares * price, 2)
    atr_stop = signal.atr_stop
    trailing_stop = round(price * (1 - TRAILING_STOP_PCT), 2)
    max_loss = round((price - atr_stop) * shares, 2)

    return PositionSizing(
        symbol=signal.symbol,
        shares=shares,
        cost=cost,
        entry_price=price,
        atr_stop=atr_stop,
        trailing_stop=trailing_stop,
        max_loss=max_loss,
        valid=True,
    )


def get_open_positions() -> list:
    """
    Returns list of current open positions from Alpaca.
    """
    return _trading_client.get_all_positions()


def get_open_position_count() -> int:
    return len(get_open_positions())


def get_account_info() -> dict:
    """
    Returns account equity and cash.
    """
    account = _trading_client.get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
    }


def is_drawdown_breach() -> bool:
    """
    Returns True if account equity has dropped 25% below the configured account size.
    Bot should pause new entries if this is True.

    Threshold = ACCOUNT_SIZE * (1 - MAX_DRAWDOWN_PCT) = $2500 * 0.75 = $1,875
    """
    try:
        info = get_account_info()
        floor = ACCOUNT_SIZE * (1 - MAX_DRAWDOWN_PCT)
        return info["equity"] < floor
    except Exception:
        return False


def check_entry(signal: SignalResult) -> tuple[bool, str]:
    """
    Final gate before placing a buy order.

    Checks:
      1. Signal is BUY
      2. Positions < MAX_POSITIONS (5)
      3. No existing position in this symbol
      4. Drawdown not breached
      5. Sufficient buying power

    Returns (approved: bool, reason: str)
    """
    if signal.signal != "BUY":
        return False, f"Signal is {signal.signal}, not BUY"

    # Check drawdown
    if is_drawdown_breach():
        return False, "Account drawdown > 25% — bot paused, no new entries"

    # Check position count
    positions = get_open_positions()
    if len(positions) >= MAX_POSITIONS:
        return False, f"At max positions ({MAX_POSITIONS})"

    # Check not already in this symbol
    existing_symbols = [p.symbol for p in positions]
    if signal.symbol in existing_symbols:
        return False, f"Already holding {signal.symbol}"

    # Check buying power
    sizing = calculate_position_size(signal)
    if not sizing.valid:
        return False, sizing.reason

    account = get_account_info()
    if account["buying_power"] < sizing.cost:
        return False, f"Insufficient buying power: ${account['buying_power']:.2f} < ${sizing.cost:.2f}"

    return True, "Entry approved"


# --- Exit checks for open positions ---

def check_exit(position, entry_data: dict) -> tuple[str, str]:
    """
    Checks whether an open position should be exited.

    Exit priority:
      1. ATR stop  — if current price < atr_stop (hard floor, never skip)
      2. Trailing stop — if current price < highest_price * (1 - 5%)
      3. SuperTrend flip — if SuperTrend flipped to bearish

    entry_data keys:
      - atr_stop: float
      - highest_price: float (updated each day as price rises)
      - st_direction: int (current ST direction from today's scan)

    Returns (action: str, reason: str)
      action = "EXIT" | "HOLD"
    """
    current_price = float(position.current_price)
    atr_stop = entry_data.get("atr_stop", 0)
    highest_price = entry_data.get("highest_price", current_price)
    st_direction = entry_data.get("st_direction", 1)

    # Update trailing high
    highest_price = max(highest_price, current_price)
    trailing_stop = round(highest_price * (1 - TRAILING_STOP_PCT), 2)

    # 1. ATR hard stop
    if atr_stop > 0 and current_price <= atr_stop:
        return "EXIT", f"ATR hard stop hit: ${current_price:.2f} <= ${atr_stop:.2f}"

    # 2. Trailing stop
    if current_price <= trailing_stop:
        return "EXIT", f"Trailing stop hit: ${current_price:.2f} <= ${trailing_stop:.2f} (5% below ${highest_price:.2f})"

    # 3. SuperTrend flip to bearish
    if st_direction == -1:
        return "EXIT", f"SuperTrend flipped bearish at ${current_price:.2f}"

    return "HOLD", f"Holding — price ${current_price:.2f}, trailing stop ${trailing_stop:.2f}"
