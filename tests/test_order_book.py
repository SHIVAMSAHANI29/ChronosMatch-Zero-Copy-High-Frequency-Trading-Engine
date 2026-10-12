from datetime import datetime, timezone
from decimal import Decimal

from src.models import Order, OrderStatus, Side
from src.order_book import OrderBook

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_seq = 0


def mk(side, price, qty=10, oid=None):
    global _seq
    _seq += 1
    return Order(oid or f"O{_seq}", "AAPL", side, price, qty, NOW, _seq)


def test_empty_book():
    book = OrderBook("AAPL")
    assert book.best_bid() is None and book.best_ask() is None
    assert book.spread() is None
    assert book.active_order_count() == 0
    assert book.snapshot() == {"symbol": "AAPL", "bids": [], "asks": []}


def test_bids_highest_first_asks_lowest_first():
    book = OrderBook("AAPL")
    for p in ("99", "101", "100"):
        book.add(mk(Side.BUY, p))
    for p in ("105", "103", "104"):
        book.add(mk(Side.SELL, p))
    assert book.best_bid() == Decimal("101")
    assert book.best_ask() == Decimal("103")
    assert book.spread() == Decimal("2")
    assert [o.price for o in book.bids.orders()] == [Decimal(x) for x in (101, 100, 99)]
    assert [o.price for o in book.asks.orders()] == [Decimal(x) for x in (103, 104, 105)]


def test_time_priority_within_a_level():
    book = OrderBook("AAPL")
    first, second, third = (mk(Side.SELL, "100") for _ in range(3))
    for o in (first, second, third):
        book.add(o)
    assert book.asks.best_order() is first
    assert list(book.asks.orders()) == [first, second, third]


def test_cancel_marks_order_and_updates_quantities():
    book = OrderBook("AAPL")
    a, b = mk(Side.BUY, "100", 5), mk(Side.BUY, "100", 7)
    book.add(a)
    book.add(b)
    assert book.cancel(a) is True
    assert a.status is OrderStatus.CANCELLED
    assert book.active_order_count() == 1
    assert book.bids.depth() == [(Decimal("100"), 7, 1)]
    assert book.bids.best_order() is b


def test_cancel_twice_returns_false():
    book = OrderBook("AAPL")
    a = mk(Side.BUY, "100")
    book.add(a)
    assert book.cancel(a) is True
    assert book.cancel(a) is False
    assert book.active_order_count() == 1 - 1


def test_cancelled_best_level_is_skipped():
    book = OrderBook("AAPL")
    top, lower = mk(Side.BUY, "101"), mk(Side.BUY, "100")
    book.add(top)
    book.add(lower)
    book.cancel(top)
    assert book.best_bid() == Decimal("100")
    assert book.bids.best_order() is lower


def test_all_cancelled_book_is_empty():
    book = OrderBook("AAPL")
    orders = [mk(Side.SELL, p) for p in ("100", "100", "101")]
    for o in orders:
        book.add(o)
    for o in orders:
        book.cancel(o)
    assert book.best_ask() is None
    assert book.asks.depth() == []
    assert list(book.asks.orders()) == []


def test_filled_resting_order_is_removed_from_top():
    book = OrderBook("AAPL")
    a, b = mk(Side.SELL, "100", 5), mk(Side.SELL, "101", 5)
    book.add(a)
    book.add(b)
    a.fill(5)
    book.asks.on_resting_fill(a, 5)
    assert book.best_ask() == Decimal("101")
    assert book.asks.best_order() is b
    assert len(book.asks) == 1


def test_depth_aggregates_and_respects_limit():
    book = OrderBook("AAPL")
    book.add(mk(Side.BUY, "100", 5))
    book.add(mk(Side.BUY, "100", 3))
    book.add(mk(Side.BUY, "99", 4))
    assert book.bids.depth() == [(Decimal("100"), 8, 2), (Decimal("99"), 4, 1)]
    assert book.bids.depth(limit=1) == [(Decimal("100"), 8, 2)]
    snap = book.snapshot(depth=1)
    assert snap["bids"] == [{"price": "100.0000", "quantity": 8, "orders": 2}]


def test_partial_fill_reduces_level_quantity():
    book = OrderBook("AAPL")
    a = mk(Side.BUY, "100", 10)
    book.add(a)
    a.fill(4)
    book.bids.on_resting_fill(a, 4)
    assert book.bids.depth() == [(Decimal("100"), 6, 1)]
    assert len(book.bids) == 1
