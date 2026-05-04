import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import TRAILING_STOP_PCT
from risk.manager import check_exit, get_open_positions
from execution.engine import close_position
from signals.generator import analyze

ET = ZoneInfo("America/New_York")

TRADES_CSV = Path("logs/trades.csv")
SCANS_CSV = Path("logs/scans.csv")
STATE_FILE = Path("logs/positions.json")   # Tracks ATR stop + highest price per symbol


# ---------------------------------------------------------------------------
# State management — persists atr_stop and highest_price across daily runs
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    """Loads position state (atr_stop, highest_price) from JSON file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state: dict) -> None:
    """Saves position state to JSON file."""
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_state_for_new_position(symbol: str, atr_stop: float, entry_price: float) -> None:
    """Called after a new buy order is placed. Records the ATR stop and entry as highest price."""
    state = _load_state()
    state[symbol] = {
        "atr_stop": atr_stop,
        "highest_price": entry_price,
    }
    _save_state(state)


def remove_state_for_symbol(symbol: str) -> None:
    """Called after a position is closed. Removes its state."""
    state = _load_state()
    state.pop(symbol, None)
    _save_state(state)


def _update_highest_price(symbol: str, current_price: float) -> None:
    """Updates highest_price if current price is a new high for the position."""
    state = _load_state()
    if symbol in state:
        state[symbol]["highest_price"] = max(state[symbol]["highest_price"], current_price)
        _save_state(state)


# ---------------------------------------------------------------------------
# Exit monitoring
# ---------------------------------------------------------------------------

def check_and_exit_positions(dry_run: bool = False) -> list:
    """
    Reviews all open positions and closes any that hit an exit condition.

    Exit priority (checked in order):
      1. ATR hard stop (entry - 2xATR)
      2. Trailing stop (5% below highest price reached)
      3. SuperTrend flipped bearish

    Returns list of exit actions taken.
    """
    positions = get_open_positions()
    state = _load_state()
    actions = []

    for position in positions:
        symbol = position.symbol
        current_price = float(position.current_price)
        qty = int(position.qty)

        # Update the highest price we've seen for trailing stop calculation
        _update_highest_price(symbol, current_price)
        state = _load_state()  # Reload after update

        # Get current SuperTrend direction from today's signal analysis
        signal = analyze(symbol)
        st_direction = signal.st_direction

        entry_data = state.get(symbol, {
            "atr_stop": 0,
            "highest_price": current_price,
        })
        entry_data["st_direction"] = st_direction

        action, reason = check_exit(position, entry_data)

        if action == "EXIT":
            print(f"  EXIT {symbol}: {reason}")
            if not dry_run:
                try:
                    close_position(symbol, reason=reason)
                    log_trade(symbol, "SELL", qty, current_price, reason=reason)
                    remove_state_for_symbol(symbol)
                    actions.append({"symbol": symbol, "action": "EXIT", "reason": reason})
                except Exception as e:
                    print(f"  ERROR closing {symbol}: {e}")
            else:
                actions.append({"symbol": symbol, "action": "EXIT (dry run)", "reason": reason})
        else:
            trailing_stop = round(entry_data["highest_price"] * (1 - TRAILING_STOP_PCT), 2)
            print(f"  HOLD {symbol}: ${current_price:.2f} | ATR stop ${entry_data.get('atr_stop', 0):.2f} | Trail ${trailing_stop:.2f} | ST {'▲' if st_direction == 1 else '▼'}")
            actions.append({"symbol": symbol, "action": "HOLD", "reason": reason})

    return actions


# ---------------------------------------------------------------------------
# CSV logging
# ---------------------------------------------------------------------------

def log_trade(
    symbol: str,
    side: str,
    shares: int,
    price: float,
    reason: str = "",
    atr_stop: float = 0.0,
    trailing_stop: float = 0.0,
) -> None:
    """Appends a trade record to logs/trades.csv."""
    TRADES_CSV.parent.mkdir(exist_ok=True)
    write_header = not TRADES_CSV.exists()

    with open(TRADES_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "date", "symbol", "side", "shares", "price", "cost",
                "atr_stop", "trailing_stop", "reason"
            ])
        writer.writerow([
            datetime.now(ET).strftime("%Y-%m-%d %H:%M"),
            symbol, side, shares,
            f"{price:.2f}",
            f"{shares * price:.2f}",
            f"{atr_stop:.2f}",
            f"{trailing_stop:.2f}",
            reason,
        ])


def log_scan(symbol: str, signal: str, price: float, st_direction: int, atr: float, reason: str) -> None:
    """Appends a scan record to logs/scans.csv."""
    SCANS_CSV.parent.mkdir(exist_ok=True)
    write_header = not SCANS_CSV.exists()

    with open(SCANS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "symbol", "signal", "price", "st_direction", "atr", "reason"])
        writer.writerow([
            datetime.now(ET).strftime("%Y-%m-%d %H:%M"),
            symbol, signal,
            f"{price:.2f}",
            st_direction,
            f"{atr:.2f}",
            reason,
        ])


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------

def print_portfolio_summary() -> None:
    """Prints current open positions with stop levels."""
    positions = get_open_positions()
    state = _load_state()

    if not positions:
        print("\n  No open positions.")
        return

    print(f"\n  {'Symbol':<8} {'Shares':>6} {'Entry':>8} {'Current':>8} {'P&L':>8} {'ATR Stop':>9} {'Trail Stop':>10} {'ST':>4}")
    print("  " + "-" * 68)

    for pos in positions:
        symbol = pos.symbol
        qty = int(pos.qty)
        current = float(pos.current_price)
        avg_entry = float(pos.avg_entry_price)
        pnl = (current - avg_entry) * qty
        s = state.get(symbol, {})
        atr_stop = s.get("atr_stop", 0)
        highest = s.get("highest_price", current)
        trail = round(highest * (1 - TRAILING_STOP_PCT), 2)

        signal = analyze(symbol)
        st_dir = "▲" if signal.st_direction == 1 else "▼"

        print(
            f"  {symbol:<8} {qty:>6} ${avg_entry:>7.2f} ${current:>7.2f} "
            f"{'$' + f'{pnl:+.2f}':>8} ${atr_stop:>8.2f} ${trail:>9.2f} {st_dir:>4}"
        )


def print_trade_history(n: int = 20) -> None:
    """Prints last N trades from trades.csv."""
    if not TRADES_CSV.exists():
        print("  No trade history yet.")
        return

    with open(TRADES_CSV) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("  No trades recorded.")
        return

    print(f"\n  Last {min(n, len(rows))} trades:")
    print(f"  {'Date':<17} {'Symbol':<8} {'Side':<5} {'Shares':>6} {'Price':>8} {'Cost':>8}  Reason")
    print("  " + "-" * 80)
    for row in rows[-n:]:
        print(
            f"  {row['date']:<17} {row['symbol']:<8} {row['side']:<5} "
            f"{row['shares']:>6} ${row['price']:>7}  ${row['cost']:>7}  {row['reason']}"
        )
