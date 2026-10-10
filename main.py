"""Command-line demonstration of the ChronosMatch Week 1 matching engine.

All prices are artificial educational examples, not real market data.
"""

import sys
from decimal import Decimal

from src.matching_engine import MatchingEngine
from src.models import InvalidOrderError, Order, Side


def fmt_price(price: Decimal) -> str:
    """Format a price like ₹1,000.00."""
    return f"₹{price:,.2f}"


def submit_and_report(engine: MatchingEngine, order: Order) -> None:
    """Submit one order and print what happened."""
    print(
        f"SUBMIT {order.order_id}: {order.side.value} {order.quantity} "
        f"{order.symbol} @ {fmt_price(order.price)}"
    )
    trades = engine.submit_order(order)
    for trade in trades:
        print(
            f"  -> TRADE #{trade.trade_id}: {trade.symbol} {trade.quantity} "
            f"@ {fmt_price(trade.price)} (buy {trade.buy_order_id}, sell {trade.sell_order_id})"
        )
    if order.remaining > 0:
        print(f"  -> {order.remaining} of {order.quantity} resting in the book")


def try_submit(
    engine: MatchingEngine, order_id: str, symbol: str, side: Side, price: object, quantity: object
) -> None:
    """Build and submit an order that may be invalid; print the rejection if so."""
    try:
        order = Order(order_id, symbol, side, price, quantity)  # type: ignore[arg-type]
        engine.submit_order(order)
    except InvalidOrderError as error:  # DuplicateOrderError is a subclass
        print(f"REJECTED {order_id}: {error}")


def print_open_orders(engine: MatchingEngine) -> None:
    """Print every open order, grouped by symbol and side, in priority order."""
    for symbol in engine.symbols():
        print(symbol)
        for side in (Side.BUY, Side.SELL):
            print(f"  {side.value} orders:")
            orders = engine.open_orders(symbol, side)
            if not orders:
                print("    (none)")
            for o in orders:
                print(
                    f"    {o.order_id}: {o.remaining}/{o.quantity} "
                    f"@ {fmt_price(o.price)} (seq {o.sequence})"
                )


def main() -> None:
    # Make the ₹ symbol print correctly even if output is redirected to a file.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    engine = MatchingEngine()

    print("=== ChronosMatch Week 1 demo ===")
    print("(artificial educational prices, not real market data)\n")

    print("--- Submitting orders ---")
    demo_orders = [
        Order("B1", "AAPL", Side.BUY, 100, 10),
        Order("S1", "AAPL", Side.SELL, 100, 4),
        Order("S2", "AAPL", Side.SELL, 99, 6),
        Order("B2", "MSFT", Side.BUY, 200, 5),
        Order("S3", "MSFT", Side.SELL, 205, 5),
    ]
    for order in demo_orders:
        submit_and_report(engine, order)

    print("\n--- Invalid and duplicate orders ---")
    try_submit(engine, "B1", "AAPL", Side.BUY, 100, 1)    # duplicate ID
    try_submit(engine, "X1", "AAPL", Side.BUY, -5, 10)    # negative price

    print("\n--- Executed trades ---")
    for t in engine.trades:
        print(
            f"#{t.trade_id} {t.symbol} {t.quantity} @ {fmt_price(t.price)} "
            f"buy={t.buy_order_id} sell={t.sell_order_id}"
        )

    print("\n--- Remaining open orders ---")
    print_open_orders(engine)

    print("\n--- Summary ---")
    print(f"Total trades: {engine.trade_count}")
    print(f"Total traded quantity: {engine.total_traded_quantity}")
    print(f"Total traded value: {fmt_price(engine.total_traded_value())}")


if __name__ == "__main__":
    main()