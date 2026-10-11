"""The matching engine: accepts limit orders and executes trades.

Rules implemented in Week 1:
  * Limit orders only.
  * Price-time priority (best price first, then earliest sequence number).
  * A BUY matches a SELL when buy price >= sell price.
  * EXECUTION PRICE RULE: a trade executes at the RESTING order's price
    (the order that was already in the book).
  * Partial fills are supported; unfilled remainders rest in the book.
  * Order IDs must be unique for the lifetime of the engine, including IDs of
    orders that have already been filled.
"""

from __future__ import annotations

import itertools
import time
from decimal import Decimal

from .models import (
    DuplicateOrderError,
    InvalidOrderError,
    Order,
    Side,
    Trade,
)
from .order_book import OrderBook


class MatchingEngine:
    """Manages one OrderBook per symbol, so different symbols never interact."""

    def __init__(self) -> None:
        self._books: dict[str, OrderBook] = {}
        self._seen_order_ids: set[str] = set()
        self._next_sequence = itertools.count(1)   # time priority: 1, 2, 3, ...
        self._next_trade_id = itertools.count(1)
        self._trades: list[Trade] = []

    # ------------------------------------------------------------------ submit
    def submit_order(self, order: Order) -> list[Trade]:
        """Accept a new order, match it, and return the trades it caused.

        Raises:
            InvalidOrderError: the order is invalid or was already used.
            DuplicateOrderError: the order ID has been seen before.

        A rejected order changes nothing: it gets no sequence number, its ID is
        not recorded, and the book is untouched.
        """
        if not isinstance(order, Order):
            raise InvalidOrderError("submit_order expects an Order object")

        order.validate()
        if order.order_id in self._seen_order_ids:
            raise DuplicateOrderError(f"Duplicate order ID: {order.order_id!r}")
        if order.remaining != order.quantity:
            raise InvalidOrderError("Cannot submit an order that is already partly filled")

        # The order is accepted from here on.
        self._seen_order_ids.add(order.order_id)
        order.sequence = next(self._next_sequence)
        order.timestamp = time.time()

        book = self._books.get(order.symbol)
        if book is None:
            book = OrderBook(order.symbol)
            self._books[order.symbol] = book

        new_trades = self._match(order, book)

        if order.remaining > 0:
            book.add(order)   # unmatched quantity rests in the book

        return new_trades

    # ---------------------------------------------------------------- matching
    @staticmethod
    def _crosses(incoming: Order, resting: Order) -> bool:
        """True if the two orders' prices allow a trade."""
        if incoming.side is Side.BUY:
            return incoming.price >= resting.price
        return incoming.price <= resting.price

    def _match(self, incoming: Order, book: OrderBook) -> list[Trade]:
        """Trade the incoming order against the best opposing orders."""
        opposite = incoming.side.opposite
        trades: list[Trade] = []

        while incoming.remaining > 0:
            resting = book.best(opposite)
            if resting is None or not self._crosses(incoming, resting):
                break   # nothing left to trade against at an acceptable price

            quantity = min(incoming.remaining, resting.remaining)

            if incoming.side is Side.BUY:
                buy_id, sell_id = incoming.order_id, resting.order_id
            else:
                buy_id, sell_id = resting.order_id, incoming.order_id

            trade = Trade(
                trade_id=next(self._next_trade_id),
                symbol=incoming.symbol,
                price=resting.price,        # resting-order pricing rule
                quantity=quantity,
                buy_order_id=buy_id,
                sell_order_id=sell_id,
                timestamp=time.time(),
            )

            incoming.remaining -= quantity
            resting.remaining -= quantity
            if resting.remaining == 0:
                book.pop_best(opposite)     # fully filled: leave the book

            trades.append(trade)
            self._trades.append(trade)

        return trades

    # ----------------------------------------------------------------- queries
    @property
    def trades(self) -> list[Trade]:
        """All executed trades so far, oldest first (returns a copy)."""
        return list(self._trades)

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def total_traded_quantity(self) -> int:
        return sum(trade.quantity for trade in self._trades)

    def symbols(self) -> list[str]:
        """Symbols that have had at least one accepted order, sorted."""
        return sorted(self._books)

    def open_orders(self, symbol: str, side: Side) -> list[Order]:
        """Open orders for a symbol and side, in priority order."""
        book = self._books.get(symbol.strip().upper())
        return book.orders(side) if book else []

    def total_traded_value(self) -> Decimal:
        """Sum of price * quantity over all trades, as a Decimal."""
        return sum((t.price * t.quantity for t in self._trades), Decimal("0"))