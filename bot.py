"""
Stock Swing Trading Bot — SuperTrend Strategy
=============================================
Runs daily after market close to:
  1. Check exits on open positions (ATR stop, trailing stop, ST flip)
  2. Scan watchlist for fresh SuperTrend bullish flips
  3. Place buy orders for approved signals

Usage:
  python3 bot.py          # Scheduled mode (runs at 4:05 PM ET daily)
  python3 bot.py --once   # Single scan (for GitHub Actions / testing)
  python3 bot.py --dry-run --once  # Scan without placing orders
"""

import warnings
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

import argparse
import logging
import schedule
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import WATCHLIST, SCAN_TIME
from signals.generator import analyze
from risk.manager import (
    calculate_position_size,
    check_entry,
    is_drawdown_breach,
    get_account_info,
    get_open_position_count,
)
from execution.engine import place_buy_order, get_account_info as engine_account
from monitor.portfolio import (
    check_and_exit_positions,
    update_state_for_new_position,
    log_trade,
    log_scan,
    print_portfolio_summary,
    print_trade_history,
)

ET = ZoneInfo("America/New_York")

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def run_scan(dry_run: bool = False) -> None:
    """
    Main scan routine:
      1. Print account summary
      2. Exit positions that hit stop/flip conditions
      3. Scan watchlist for BUY signals
      4. Place orders for approved signals (unless dry_run)
    """
    now = datetime.now(ET)
    log.info("=" * 60)
    log.info(f"Stock Swing Bot — {now.strftime('%Y-%m-%d %H:%M ET')}")
    if dry_run:
        log.info("*** DRY RUN — no orders will be placed ***")
    log.info("=" * 60)

    # --- Account info ---
    try:
        account = get_account_info()
        log.info(f"Account equity: ${account['equity']:.2f} | Cash: ${account['cash']:.2f} | Buying power: ${account['buying_power']:.2f}")
    except Exception as e:
        log.error(f"Could not fetch account info: {e}")

    # --- Drawdown check ---
    if is_drawdown_breach():
        log.warning("⚠️  Account drawdown > 25%. Skipping new entries today.")
        _run_exits_only(dry_run)
        return

    # --- Step 1: Exit checks ---
    log.info("\n--- Checking open positions for exits ---")
    exit_actions = check_and_exit_positions(dry_run=dry_run)
    if not exit_actions:
        log.info("  No open positions to check.")

    # --- Step 2: Portfolio summary ---
    log.info("\n--- Current Portfolio ---")
    print_portfolio_summary()

    # --- Step 3: Scan watchlist ---
    log.info(f"\n--- Scanning {len(WATCHLIST)} symbols for BUY signals ---")

    buy_signals = []
    errors = []

    for symbol in WATCHLIST:
        try:
            result = analyze(symbol)
            log_scan(
                symbol=symbol,
                signal=result.signal,
                price=result.latest_price,
                st_direction=result.st_direction,
                atr=result.atr,
                reason="; ".join(result.reasons),
            )

            if result.signal == "BUY":
                log.info(f"  🟢 BUY signal: {symbol} @ ${result.latest_price:.2f} | ATR stop ${result.atr_stop:.2f}")
                buy_signals.append(result)
            elif result.signal == "ERROR":
                errors.append(f"{symbol}: {'; '.join(result.reasons)}")

        except Exception as e:
            log.error(f"  Error scanning {symbol}: {e}")
            errors.append(f"{symbol}: {e}")

    log.info(f"\n  Found {len(buy_signals)} BUY signal(s), {len(errors)} error(s)")

    # --- Step 4: Place orders ---
    if buy_signals:
        log.info("\n--- Processing BUY signals ---")

    orders_placed = 0
    for signal in buy_signals:
        approved, reason = check_entry(signal)
        if not approved:
            log.info(f"  SKIP {signal.symbol}: {reason}")
            continue

        sizing = calculate_position_size(signal)
        if not sizing.valid:
            log.info(f"  SKIP {signal.symbol}: {sizing.reason}")
            continue

        log.info(
            f"  ORDER {signal.symbol}: {sizing.shares} shares @ ~${sizing.entry_price:.2f} "
            f"= ${sizing.cost:.2f} | ATR stop ${sizing.atr_stop:.2f} | Trail ${sizing.trailing_stop:.2f}"
        )

        if not dry_run:
            try:
                order = place_buy_order(sizing)
                update_state_for_new_position(
                    signal.symbol,
                    atr_stop=sizing.atr_stop,
                    entry_price=sizing.entry_price,
                )
                log_trade(
                    symbol=signal.symbol,
                    side="BUY",
                    shares=sizing.shares,
                    price=sizing.entry_price,
                    atr_stop=sizing.atr_stop,
                    trailing_stop=sizing.trailing_stop,
                    reason="; ".join(signal.reasons),
                )
                log.info(f"  ✅ Order placed: {order['order_id']} — {order['status']}")
                orders_placed += 1
            except Exception as e:
                log.error(f"  ❌ Order failed for {signal.symbol}: {e}")
        else:
            orders_placed += 1
            log.info(f"  [DRY RUN] Would buy {sizing.shares} shares of {signal.symbol}")

    # --- Summary ---
    log.info("\n--- Scan Complete ---")
    log.info(f"  BUY signals found: {len(buy_signals)}")
    log.info(f"  Orders placed:     {orders_placed}")
    log.info(f"  Errors:            {len(errors)}")
    if errors:
        for err in errors[:5]:
            log.warning(f"    {err}")

    log.info("\n--- Trade History ---")
    print_trade_history(n=10)
    log.info("=" * 60)


def _run_exits_only(dry_run: bool) -> None:
    """Runs only exit checks — used when drawdown is breached."""
    log.info("\n--- Checking exits only (drawdown pause active) ---")
    check_and_exit_positions(dry_run=dry_run)
    print_portfolio_summary()


def main():
    parser = argparse.ArgumentParser(description="Stock Swing Trading Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit (for GitHub Actions)")
    parser.add_argument("--dry-run", action="store_true", help="Scan without placing orders")
    args = parser.parse_args()

    if args.once:
        run_scan(dry_run=args.dry_run)
    else:
        log.info(f"Scheduled mode: will run at {SCAN_TIME} ET on weekdays")
        schedule.every().monday.at(SCAN_TIME).do(run_scan, dry_run=args.dry_run)
        schedule.every().tuesday.at(SCAN_TIME).do(run_scan, dry_run=args.dry_run)
        schedule.every().wednesday.at(SCAN_TIME).do(run_scan, dry_run=args.dry_run)
        schedule.every().thursday.at(SCAN_TIME).do(run_scan, dry_run=args.dry_run)
        schedule.every().friday.at(SCAN_TIME).do(run_scan, dry_run=args.dry_run)

        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    main()
