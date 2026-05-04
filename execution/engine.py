import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus

from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER
from risk.manager import PositionSizing

_trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)


def place_buy_order(sizing: PositionSizing) -> dict:
    """
    Places a market buy order for the given position sizing.

    Uses market order for immediate execution at close.
    Returns order details dict.

    Raises RuntimeError if order fails.
    """
    if not sizing.valid or sizing.shares < 1:
        raise RuntimeError(f"Invalid sizing for {sizing.symbol}: {sizing.reason}")

    order_request = MarketOrderRequest(
        symbol=sizing.symbol,
        qty=sizing.shares,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
    )

    try:
        order = _trading_client.submit_order(order_request)
        return {
            "order_id": str(order.id),
            "symbol": sizing.symbol,
            "shares": sizing.shares,
            "entry_price": sizing.entry_price,
            "atr_stop": sizing.atr_stop,
            "trailing_stop": sizing.trailing_stop,
            "cost": sizing.cost,
            "status": str(order.status),
        }
    except Exception as e:
        raise RuntimeError(f"Failed to place buy order for {sizing.symbol}: {e}")


def place_sell_order(symbol: str, shares: int, reason: str = "") -> dict:
    """
    Places a market sell order to close a position.

    Returns order details dict.
    Raises RuntimeError if order fails.
    """
    order_request = MarketOrderRequest(
        symbol=symbol,
        qty=shares,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )

    try:
        order = _trading_client.submit_order(order_request)
        return {
            "order_id": str(order.id),
            "symbol": symbol,
            "shares": shares,
            "status": str(order.status),
            "reason": reason,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to place sell order for {symbol}: {e}")


def close_position(symbol: str, reason: str = "") -> dict:
    """
    Closes the full position in a symbol using Alpaca's close_position shortcut.
    """
    try:
        response = _trading_client.close_position(symbol)
        return {
            "symbol": symbol,
            "status": "closed",
            "reason": reason,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to close position {symbol}: {e}")


def get_account_info() -> dict:
    account = _trading_client.get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "portfolio_value": float(account.portfolio_value),
    }


def get_open_orders() -> list:
    request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
    return _trading_client.get_orders(request)
