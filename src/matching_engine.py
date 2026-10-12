"""The matching engine: price-time priority matching of limit orders.

Execution-price rule
--------------------
A trade executes at the **resting order's price** (the order that was already
in the book). Example: a resting SELL at 100 and an incoming BUY limit 102
trade at 100; the buyer gets price improvement.

Concurrency model
-----------------
All state changes happen inside :meth:`MatchingEngine.submit` and
:meth:`MatchingEngine.cancel`, which are synchronous (no ``await``) and run
under one re-entrant lock. That gives a single authoritative, serialised
execution path:

* sequence numbers are unique and strictly increasing,
* a cancel and a match for the same order can never interleave: whichever
  call acquires the lock first wins and the other sees the updated state,
* the same input sequence always produces the same trades (deterministic).

Event listeners are called *inside* the lock so events are delivered in the
exact order the engine produced them. Listeners must therefore be fast and
non-blocking (the WebSocket layer only enqueues).

This is an educational engine, not an exchange-grade system.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Callable

from .models import (
    DuplicateOrderError,
    Order,
    OrderStatus,
    OrderValidationError,
    Side,
    Trade,
    validate_symbol,
)
from .order_book import OrderBook

__all__ = [
    "MatchingEngine",
    "SubmitResult",
    "CancelResult",
    "CancelStatus",
    "EngineEvent",
    "EventType",
    "InvariantViolation",
]

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(StrEnum):
    ORDER_ACCEPTED = "order_accepted"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    TRADE_EXECUTED = "trade_executed"
    BOOK_UPDATED = "book_updated"


@dataclass(frozen=True, slots=True)
class EngineEvent:
    """A change published by the engine: type, timestamp and payload."""

    type: EventType
    symbol: str
    timestamp: datetime
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }


@dataclass(slots=True)
class SubmitResult:
    """Outcome of an accepted order.

    ``order`` is the live engine object (do not mutate it). ``events`` is
    only populated while at least one listener is subscribed.
    """

    order: Order
    trades: list[Trade] = field(default_factory=list)
    events: list[EngineEvent] = field(default_factory=list)


class CancelStatus(StrEnum):
    CANCELLED = "CANCELLED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_FILLED = "ALREADY_FILLED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"


@dataclass(frozen=True, slots=True)
class CancelResult:
    status: CancelStatus
    order_id: str
    order: Order | None = None
    events: tuple[EngineEvent, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is CancelStatus.CANCELLED

    @property
    def message(self) -> str:
        return {
            CancelStatus.CANCELLED: "order cancelled",
            CancelStatus.NOT_FOUND: "order not found",
            CancelStatus.ALREADY_FILLED: "order is already fully filled and cannot be cancelled",
            CancelStatus.ALREADY_CANCELLED: "order was already cancelled",
        }[self.status]


class InvariantViolation(AssertionError):
    """Raised by :meth:`MatchingEngine.check_invariants` when state is inconsistent."""


class MatchingEngine:
    """Multi-symbol limit-order matching engine (price-time priority)."""

    BOOK_EVENT_DEPTH = 10

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or _utc_now
        self._lock = threading.RLock()
        self._books: dict[str, OrderBook] = {}
        self._orders: dict[str, Order] = {}  # every order ever accepted, by id
        self._trades: list[Trade] = []
        self._order_seq = 0
        self._trade_seq = 0
        self._id_counter = 0
        self._traded_quantity = 0
        self._cancelled_count = 0
        self._rejected_count = 0
        self._listeners: list[Callable[[EngineEvent], None]] = []

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def subscribe(self, listener: Callable[[EngineEvent], None]) -> None:
        """Register a callback invoked for every event (inside the engine lock)."""
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[EngineEvent], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _publish(self, events: list[EngineEvent]) -> None:
        for listener in tuple(self._listeners):
            for event in events:
                try:
                    listener(event)
                except Exception:  # a broken listener must never break matching
                    logger.exception("event listener failed")

    def _order_event(self, order: Order, now: datetime) -> EngineEvent:
        if order.status is OrderStatus.FILLED:
            kind = EventType.ORDER_FILLED
        else:
            kind = EventType.ORDER_PARTIALLY_FILLED
        return EngineEvent(kind, order.symbol, now, order.to_dict())

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def _generate_order_id(self) -> str:
        while True:
            self._id_counter += 1
            candidate = f"ORD-{self._id_counter:08d}"
            if candidate not in self._orders:
                return candidate

    def submit(
        self,
        symbol: str,
        side: Side | str,
        price: Decimal | int | str,
        quantity: int,
        order_id: str | None = None,
    ) -> SubmitResult:
        """Validate, match and (if needed) rest a new limit order.

        Raises :class:`OrderValidationError` for bad input and
        :class:`DuplicateOrderError` for a reused ID. A rejected order does
        not consume a sequence number or change any state.
        """
        with self._lock:
            # 1-3. validate, check ID, assign sequence (validation happens in Order)
            if order_id is None:
                order_id = self._generate_order_id()
            elif isinstance(order_id, str) and order_id in self._orders:
                self._rejected_count += 1
                raise DuplicateOrderError(f"order id {order_id!r} already exists")
            now = self._clock()
            try:
                order = Order(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,  # type: ignore[arg-type]
                    price=price,  # type: ignore[arg-type]
                    quantity=quantity,
                    timestamp=now,
                    sequence=self._order_seq + 1,
                )
            except OrderValidationError:
                self._rejected_count += 1
                raise
            self._order_seq += 1
            self._orders[order.order_id] = order

            book = self._books.get(order.symbol)
            if book is None:
                book = self._books[order.symbol] = OrderBook(order.symbol)

            emit = bool(self._listeners)
            events: list[EngineEvent] = []
            if emit:
                events.append(
                    EngineEvent(EventType.ORDER_ACCEPTED, order.symbol, now, order.to_dict())
                )

            # 4-10. match against the best opposing orders while prices cross
            trades: list[Trade] = []
            is_buy = order.side is Side.BUY
            opposing = book.opposite(order.side)
            limit = order.price
            while order.remaining:  # type: ignore[truthy-bool]
                resting = opposing.best_order()
                if resting is None:
                    break
                if is_buy:
                    if resting.price > limit:
                        break
                elif resting.price < limit:
                    break

                qty = min(order.remaining, resting.remaining)  # type: ignore[type-var]
                self._trade_seq += 1
                trade_time = self._clock()
                trade = Trade(
                    trade_id=f"TRD-{self._trade_seq:08d}",
                    symbol=order.symbol,
                    price=resting.price,  # execution price = resting order's price
                    quantity=qty,
                    buy_order_id=order.order_id if is_buy else resting.order_id,
                    sell_order_id=resting.order_id if is_buy else order.order_id,
                    timestamp=trade_time,
                    sequence=self._trade_seq,
                )
                order.fill(qty)
                resting.fill(qty)
                opposing.on_resting_fill(resting, qty)
                self._traded_quantity += qty
                self._trades.append(trade)
                trades.append(trade)
                if emit:
                    events.append(
                        EngineEvent(EventType.TRADE_EXECUTED, trade.symbol, trade_time, trade.to_dict())
                    )
                    events.append(self._order_event(resting, trade_time))

            # 11. rest any unmatched remainder
            if order.remaining:
                book.add(order)

            # 12. publish
            if emit:
                if trades:
                    events.append(self._order_event(order, self._clock()))
                events.append(
                    EngineEvent(
                        EventType.BOOK_UPDATED,
                        order.symbol,
                        self._clock(),
                        book.snapshot(self.BOOK_EVENT_DEPTH),
                    )
                )
                self._publish(events)

            return SubmitResult(order=order, trades=trades, events=events)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------
    def cancel(self, order_id: str) -> CancelResult:
        """Cancel an active order. Never silently cancels a finished order."""
        with self._lock:
            order = self._orders.get(order_id) if isinstance(order_id, str) else None
            if order is None:
                return CancelResult(CancelStatus.NOT_FOUND, str(order_id))
            if order.status is OrderStatus.FILLED:
                return CancelResult(CancelStatus.ALREADY_FILLED, order_id, order)
            if order.status is OrderStatus.CANCELLED:
                return CancelResult(CancelStatus.ALREADY_CANCELLED, order_id, order)

            book = self._books[order.symbol]
            book.cancel(order)
            self._cancelled_count += 1

            events: list[EngineEvent] = []
            if self._listeners:
                now = self._clock()
                events = [
                    EngineEvent(EventType.ORDER_CANCELLED, order.symbol, now, order.to_dict()),
                    EngineEvent(
                        EventType.BOOK_UPDATED, order.symbol, now, book.snapshot(self.BOOK_EVENT_DEPTH)
                    ),
                ]
                self._publish(events)
            return CancelResult(CancelStatus.CANCELLED, order_id, order, tuple(events))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id) if isinstance(order_id, str) else None

    def get_orders(
        self,
        symbol: str | None = None,
        side: Side | str | None = None,
        active_only: bool = True,
    ) -> list[Order]:
        """Orders sorted by sequence (oldest first). Raises on a bad symbol/side."""
        sym = validate_symbol(symbol) if symbol is not None else None
        sd = Side(side.strip().upper()) if isinstance(side, str) else side
        with self._lock:
            if active_only:
                if sym is not None:
                    books = [self._books[sym]] if sym in self._books else []
                else:
                    books = list(self._books.values())
                found = [o for b in books for o in b.orders()]
            else:
                found = [o for o in self._orders.values() if sym is None or o.symbol == sym]
            if sd is not None:
                found = [o for o in found if o.side is sd]
            found.sort(key=lambda o: o.sequence)
            return found

    def recent_trades(self, limit: int = 50, symbol: str | None = None) -> list[Trade]:
        """Most recent trades first."""
        sym = validate_symbol(symbol) if symbol is not None else None
        with self._lock:
            if sym is None:
                return self._trades[::-1][:limit]
            out: list[Trade] = []
            for trade in reversed(self._trades):
                if trade.symbol == sym:
                    out.append(trade)
                    if len(out) >= limit:
                        break
            return out

    @property
    def trades(self) -> list[Trade]:
        """All trades in execution order (a copy)."""
        with self._lock:
            return list(self._trades)

    def order_book_snapshot(self, symbol: str, depth: int | None = None) -> dict[str, Any]:
        sym = validate_symbol(symbol)
        with self._lock:
            book = self._books.get(sym)
            return book.snapshot(depth) if book else {"symbol": sym, "bids": [], "asks": []}

    def get_book(self, symbol: str) -> OrderBook | None:
        with self._lock:
            return self._books.get(validate_symbol(symbol))

    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._books)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            buys = sum(len(b.bids) for b in self._books.values())
            sells = sum(len(b.asks) for b in self._books.values())
            return {
                "orders_accepted": len(self._orders),
                "orders_rejected": self._rejected_count,
                "orders_cancelled": self._cancelled_count,
                "trades": len(self._trades),
                "traded_quantity": self._traded_quantity,
                "active_orders": buys + sells,
                "active_buy_orders": buys,
                "active_sell_orders": sells,
                "symbols": sorted(self._books),
            }

    # ------------------------------------------------------------------
    # Self-check (used heavily by tests)
    # ------------------------------------------------------------------
    def check_invariants(self) -> None:
        """Raise :class:`InvariantViolation` if any consistency rule is broken."""
        with self._lock:
            filled: dict[str, int] = defaultdict(int)
            last_seq = 0
            for trade in self._trades:
                if trade.sequence <= last_seq:
                    raise InvariantViolation("trade sequence is not strictly increasing")
                last_seq = trade.sequence
                buy = self._orders[trade.buy_order_id]
                sell = self._orders[trade.sell_order_id]
                if buy.side is not Side.BUY or sell.side is not Side.SELL:
                    raise InvariantViolation(f"{trade.trade_id}: wrong sides")
                if not (buy.symbol == sell.symbol == trade.symbol):
                    raise InvariantViolation(f"{trade.trade_id}: cross-symbol trade")
                if not (sell.price <= trade.price <= buy.price):
                    raise InvariantViolation(f"{trade.trade_id}: price outside both limits")
                filled[trade.buy_order_id] += trade.quantity
                filled[trade.sell_order_id] += trade.quantity

            live_per_book: dict[str, int] = defaultdict(int)
            for order in self._orders.values():
                rem, qty = order.remaining, order.quantity
                if not 0 <= rem <= qty:  # type: ignore[operator]
                    raise InvariantViolation(f"{order.order_id}: remaining out of range")
                if qty - rem != filled[order.order_id]:  # type: ignore[operator]
                    raise InvariantViolation(f"{order.order_id}: trades do not match fills")
                st = order.status
                if st is OrderStatus.NEW and rem != qty:
                    raise InvariantViolation(f"{order.order_id}: NEW but partly filled")
                if st is OrderStatus.PARTIALLY_FILLED and not 0 < rem < qty:  # type: ignore[operator]
                    raise InvariantViolation(f"{order.order_id}: bad PARTIALLY_FILLED state")
                if st is OrderStatus.FILLED and rem != 0:
                    raise InvariantViolation(f"{order.order_id}: FILLED with quantity left")
                if st is OrderStatus.CANCELLED and rem == 0:
                    raise InvariantViolation(f"{order.order_id}: CANCELLED but fully filled")
                if order.is_active:
                    live_per_book[order.symbol] += 1

            for symbol, book in self._books.items():
                if book.active_order_count() != live_per_book[symbol]:
                    raise InvariantViolation(f"{symbol}: book count differs from active orders")
                if len(list(book.orders())) != book.active_order_count():
                    raise InvariantViolation(f"{symbol}: book iteration differs from counter")
                bid, ask = book.best_bid(), book.best_ask()
                if bid is not None and ask is not None and bid >= ask:
                    raise InvariantViolation(f"{symbol}: book is crossed ({bid} >= {ask})")
                for side in (book.bids, book.asks):
                    real_by_price: dict[Decimal, int] = defaultdict(int)
                    for o in side.orders():
                        real_by_price[o.price] += o.remaining  # type: ignore[operator]
                    shown = {price: qty for price, qty, _ in side.depth()}
                    if dict(real_by_price) != shown:
                        raise InvariantViolation(f"{symbol}: level quantities do not match orders")
