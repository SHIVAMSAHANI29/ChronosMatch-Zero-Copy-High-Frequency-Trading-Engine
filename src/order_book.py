"""Per-symbol order book with price-time priority.

Data structure (one :class:`BookSide` per side of each symbol)
---------------------------------------------------------------
* ``_levels``: ``dict[price, deque[Order]]``. One FIFO queue per price level.
  Orders at the same price are served in arrival order (time priority).
* ``_heap``: a binary heap of price keys, so the best price is always at
  ``heap[0]``. Sells use the price itself (min-heap = lowest ask first); buys
  use the *negated* price (so Python's min-heap yields the highest bid first).
* ``_level_qty``: live (unfilled, uncancelled) quantity at each price level.

Lazy deletion
-------------
Cancelling an order marks it ``CANCELLED`` and subtracts its remaining
quantity from the level total, but does **not** remove it from its deque
(that would be O(n)). Dead orders (cancelled or filled) are discarded when
they reach the front of their queue. Heap entries and ``_levels`` entries are
created and removed together, so the heap never holds stale prices.

Complexity (P = number of distinct price levels on one side)
------------------------------------------------------------
* add order:        O(1) at an existing level, O(log P) when a level is created
* best price/order: amortised O(1) (dead entries are removed once each)
* cancel:           O(1) to mark; physical removal is deferred and amortised
* consume front:    O(1); O(log P) when a level empties and is popped
* depth snapshot:   O(P log P + N) (sorting levels, counting live orders)

Known trade-off: a level that contains *only* cancelled orders and is not at
the top of the book keeps its (dead) objects until it reaches the top.
"""

from __future__ import annotations

import heapq
from collections import deque
from decimal import Decimal
from typing import Any, Iterator

from .models import Order, OrderStatus, Side

__all__ = ["BookSide", "OrderBook"]


class BookSide:
    """All resting orders on one side (bids or asks) of one symbol."""

    __slots__ = ("is_buy", "_levels", "_heap", "_level_qty", "_live")

    def __init__(self, side: Side) -> None:
        self.is_buy = side is Side.BUY
        self._levels: dict[Decimal, deque[Order]] = {}
        self._heap: list[Decimal] = []
        self._level_qty: dict[Decimal, int] = {}
        self._live = 0

    def __len__(self) -> int:
        """Number of live (active) resting orders."""
        return self._live

    # -- internals -----------------------------------------------------
    def _clean_top(self) -> Decimal | None:
        """Drop dead orders/levels from the top; return the best live price."""
        heap, levels, is_buy = self._heap, self._levels, self.is_buy
        while heap:
            key = heap[0]
            price = -key if is_buy else key
            level = levels[price]
            while level and not level[0].is_active:
                level.popleft()
            if level:
                return price
            del levels[price]
            del self._level_qty[price]
            heapq.heappop(heap)
        return None

    # -- mutation ------------------------------------------------------
    def add(self, order: Order) -> None:
        """Rest *order* at the back of its price level's queue."""
        price = order.price
        level = self._levels.get(price)
        if level is None:
            level = deque()
            self._levels[price] = level
            self._level_qty[price] = 0
            heapq.heappush(self._heap, -price if self.is_buy else price)
        level.append(order)
        self._level_qty[price] += order.remaining  # type: ignore[operator]
        self._live += 1

    def on_resting_fill(self, order: Order, quantity: int) -> None:
        """Book-keeping after a resting order executed *quantity* shares.

        The caller must already have called ``order.fill(quantity)``. A fully
        filled order is physically removed lazily by :meth:`_clean_top`.
        """
        self._level_qty[order.price] -= quantity
        if order.remaining == 0:
            self._live -= 1

    def cancel(self, order: Order) -> bool:
        """Cancel a resting order. Returns False if it was not active."""
        if not order.is_active:
            return False
        order.status = OrderStatus.CANCELLED
        self._level_qty[order.price] -= order.remaining  # type: ignore[operator]
        self._live -= 1
        return True

    # -- queries -------------------------------------------------------
    def best_price(self) -> Decimal | None:
        return self._clean_top()

    def best_order(self) -> Order | None:
        """The order that must trade next (best price, then earliest)."""
        price = self._clean_top()
        return None if price is None else self._levels[price][0]

    def _live_prices(self) -> list[Decimal]:
        return sorted(
            (p for p, qty in self._level_qty.items() if qty > 0),
            reverse=self.is_buy,
        )

    def orders(self) -> Iterator[Order]:
        """Live orders in strict priority order (best price, then time)."""
        for price in self._live_prices():
            for order in self._levels[price]:
                if order.is_active:
                    yield order

    def depth(self, limit: int | None = None) -> list[tuple[Decimal, int, int]]:
        """Aggregated levels, best first: ``(price, total_quantity, order_count)``."""
        prices = self._live_prices()
        if limit is not None:
            prices = prices[:limit]
        return [
            (p, self._level_qty[p], sum(1 for o in self._levels[p] if o.is_active))
            for p in prices
        ]


class OrderBook:
    """The bid and ask sides for a single symbol."""

    __slots__ = ("symbol", "bids", "asks")

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids = BookSide(Side.BUY)
        self.asks = BookSide(Side.SELL)

    def side(self, side: Side) -> BookSide:
        return self.bids if side is Side.BUY else self.asks

    def opposite(self, side: Side) -> BookSide:
        return self.asks if side is Side.BUY else self.bids

    def add(self, order: Order) -> None:
        self.side(order.side).add(order)

    def cancel(self, order: Order) -> bool:
        return self.side(order.side).cancel(order)

    def best_bid(self) -> Decimal | None:
        return self.bids.best_price()

    def best_ask(self) -> Decimal | None:
        return self.asks.best_price()

    def spread(self) -> Decimal | None:
        bid, ask = self.best_bid(), self.best_ask()
        return None if bid is None or ask is None else ask - bid

    def active_order_count(self) -> int:
        return len(self.bids) + len(self.asks)

    def orders(self) -> list[Order]:
        """All live orders: bids (best first) then asks (best first)."""
        return [*self.bids.orders(), *self.asks.orders()]

    def snapshot(self, depth: int | None = None) -> dict[str, Any]:
        """JSON-friendly aggregated view of the book."""

        def levels(side: BookSide) -> list[dict[str, Any]]:
            return [
                {"price": str(p), "quantity": q, "orders": n}
                for p, q, n in side.depth(depth)
            ]

        return {"symbol": self.symbol, "bids": levels(self.bids), "asks": levels(self.asks)}
