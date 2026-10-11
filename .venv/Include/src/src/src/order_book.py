"""The order book: stores resting orders for ONE symbol in priority order.

This module decides WHERE orders are stored and in WHAT order. It never
executes trades; that is the matching engine's job.
"""

from __future__ import annotations

import heapq
from decimal import Decimal

from .models import Order, Side

# Each heap entry is (price_key, sequence, order).
#   BUY  price_key = -price  -> highest price becomes the smallest key (top of heap)
#   SELL price_key = +price  -> lowest price is the smallest key (top of heap)
# Ties on price are broken by the smaller (earlier) sequence number.
# Sequence numbers are unique, so the Order itself is never compared.
_HeapEntry = tuple[Decimal, int, Order]


class OrderBook:
    """Holds the open BUY and SELL orders for a single symbol."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._buys: list[_HeapEntry] = []
        self._sells: list[_HeapEntry] = []

    def _heap(self, side: Side) -> list[_HeapEntry]:
        return self._buys if side is Side.BUY else self._sells

    def add(self, order: Order) -> None:
        """Place an order with remaining quantity into the book."""
        if order.symbol != self.symbol:
            raise ValueError(
                f"Order for {order.symbol} cannot be added to the {self.symbol} book"
            )
        if order.sequence <= 0:
            raise ValueError("Order must have a positive sequence number before being added")
        if order.remaining <= 0:
            raise ValueError("Cannot add a fully filled order to the book")

        key = -order.price if order.side is Side.BUY else order.price
        heapq.heappush(self._heap(order.side), (key, order.sequence, order))

    def best(self, side: Side) -> Order | None:
        """Return (without removing) the highest-priority order on a side."""
        heap = self._heap(side)
        return heap[0][2] if heap else None

    def pop_best(self, side: Side) -> Order:
        """Remove and return the highest-priority order on a side."""
        heap = self._heap(side)
        if not heap:
            raise IndexError(f"No {side.value} orders in the {self.symbol} book")
        return heapq.heappop(heap)[2]

    def orders(self, side: Side) -> list[Order]:
        """Return the open orders on one side, in priority order.

        This builds a NEW sorted list (a copy), so it is meant for display and
        tests, not for the hot matching path.
        """
        entries = sorted(self._heap(side), key=lambda entry: (entry[0], entry[1]))
        return [entry[2] for entry in entries]

    def __len__(self) -> int:
        return len(self._buys) + len(self._sells)