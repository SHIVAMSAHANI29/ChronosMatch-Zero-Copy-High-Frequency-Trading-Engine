"""Optional baseline benchmark for ChronosMatch.

Run:  python benchmark.py --orders 50000

WHAT IS MEASURED (two separate timings):
  1. Order creation: building Order objects, which includes validation.
  2. Matching: engine.submit_order() for every order, which includes validation
     again, duplicate check, matching, and resting leftovers in the book.
The random data generation (random.choice etc.) happens inside the creation
timing. Results depend on your machine; this script prints measurements and
does not assume any numbers.
"""

import argparse
import random
import time
from decimal import Decimal

from src.matching_engine import MatchingEngine
from src.models import Order, Side


def build_orders(count: int, symbols: list[str], seed: int) -> list[Order]:
    """Create `count` random limit orders with prices near 100."""
    rng = random.Random(seed)   # fixed seed -> same orders every run
    orders = []
    for i in range(count):
        orders.append(
            Order(
                order_id=f"O{i}",
                symbol=rng.choice(symbols),
                side=rng.choice((Side.BUY, Side.SELL)),
                price=Decimal(rng.randint(95, 105)),
                quantity=rng.randint(1, 100),
            )
        )
    return orders


def main() -> None:
    parser = argparse.ArgumentParser(description="ChronosMatch baseline benchmark")
    parser.add_argument("--orders", type=int, default=20000, help="number of orders")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    args = parser.parse_args()
    if args.orders <= 0:
        parser.error("--orders must be positive")

    symbols = ["AAPL", "MSFT", "GOOG"]

    start = time.perf_counter()
    orders = build_orders(args.orders, symbols, args.seed)
    creation_time = time.perf_counter() - start

    engine = MatchingEngine()
    start = time.perf_counter()
    for order in orders:
        engine.submit_order(order)
    matching_time = time.perf_counter() - start

    open_count = sum(
        len(engine.open_orders(sym, side)) for sym in engine.symbols() for side in Side
    )

    print(f"Orders processed:        {args.orders}")
    print(f"Order creation time:     {creation_time:.4f} s (includes random data + validation)")
    print(f"Matching time:           {matching_time:.4f} s (submit_order for all orders)")
    print(f"Creation + matching:     {creation_time + matching_time:.4f} s")
    if matching_time > 0:
        print(f"Matching throughput:     {args.orders / matching_time:,.0f} orders/s")
    print(f"Trades executed:         {engine.trade_count}")
    print(f"Orders still open:       {open_count}")


if __name__ == "__main__":
    main()