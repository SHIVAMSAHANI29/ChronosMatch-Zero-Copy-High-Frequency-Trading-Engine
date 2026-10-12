import threading
from decimal import Decimal

from src.matching_engine import CancelStatus, EventType
from src.models import OrderStatus


def test_cancel_open_order(engine):
    engine.submit("AAPL", "BUY", "100", 10, order_id="B1")
    res = engine.cancel("B1")
    assert res.ok and res.status is CancelStatus.CANCELLED
    assert res.order.status is OrderStatus.CANCELLED
    assert engine.order_book_snapshot("AAPL")["bids"] == []
    assert engine.stats()["active_orders"] == 0
    assert engine.stats()["orders_cancelled"] == 1
    engine.check_invariants()


def test_cancelled_order_never_trades(engine):
    engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
    engine.cancel("S1")
    res = engine.submit("AAPL", "BUY", "100", 10)
    assert res.trades == []
    assert res.order.status is OrderStatus.NEW


def test_cancel_skips_to_next_order_in_queue(engine):
    engine.submit("AAPL", "SELL", "100", 5, order_id="S1")
    engine.submit("AAPL", "SELL", "100", 5, order_id="S2")
    engine.cancel("S1")
    res = engine.submit("AAPL", "BUY", "100", 5)
    assert [t.sell_order_id for t in res.trades] == ["S2"]


def test_cancel_unknown_order(engine):
    res = engine.cancel("missing")
    assert res.status is CancelStatus.NOT_FOUND and not res.ok
    assert "not found" in res.message


def test_cancel_filled_order_is_refused_not_silent(engine):
    engine.submit("AAPL", "SELL", "100", 5, order_id="S1")
    engine.submit("AAPL", "BUY", "100", 5, order_id="B1")
    for oid in ("S1", "B1"):
        res = engine.cancel(oid)
        assert res.status is CancelStatus.ALREADY_FILLED
        assert engine.get_order(oid).status is OrderStatus.FILLED
    assert engine.stats()["orders_cancelled"] == 0


def test_cancel_twice(engine):
    engine.submit("AAPL", "BUY", "100", 5, order_id="B1")
    assert engine.cancel("B1").ok
    again = engine.cancel("B1")
    assert again.status is CancelStatus.ALREADY_CANCELLED
    assert engine.stats()["orders_cancelled"] == 1


def test_cancel_after_partial_fill_keeps_trades_and_cancels_remainder(engine):
    engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
    engine.submit("AAPL", "BUY", "100", 4, order_id="B1")
    res = engine.cancel("S1")
    assert res.ok
    s1 = engine.get_order("S1")
    assert (s1.status, s1.remaining, s1.filled_quantity) == (OrderStatus.CANCELLED, 6, 4)
    assert len(engine.trades) == 1 and engine.trades[0].quantity == 4
    assert engine.order_book_snapshot("AAPL")["asks"] == []
    engine.check_invariants()


def test_partially_filled_incoming_order_can_be_cancelled(engine):
    engine.submit("AAPL", "SELL", "100", 4)
    engine.submit("AAPL", "BUY", "100", 10, order_id="B1")  # 6 left resting
    assert engine.get_order("B1").status is OrderStatus.PARTIALLY_FILLED
    assert engine.cancel("B1").ok
    assert engine.order_book_snapshot("AAPL")["bids"] == []
    engine.check_invariants()


def test_cancel_best_level_exposes_next_level(engine):
    engine.submit("AAPL", "BUY", "101", 5, order_id="top")
    engine.submit("AAPL", "BUY", "100", 5, order_id="next")
    engine.cancel("top")
    res = engine.submit("AAPL", "SELL", "100", 5)
    assert res.trades[0].buy_order_id == "next"
    assert res.trades[0].price == Decimal("100")


def test_cancel_non_string_id(engine):
    assert engine.cancel(None).status is CancelStatus.NOT_FOUND  # type: ignore[arg-type]


def test_cancel_events(engine):
    engine.submit("AAPL", "BUY", "100", 5, order_id="B1")
    seen = []
    engine.subscribe(seen.append)
    engine.cancel("B1")
    assert [e.type for e in seen] == [EventType.ORDER_CANCELLED, EventType.BOOK_UPDATED]
    # a refused cancel publishes nothing
    seen.clear()
    engine.cancel("B1")
    assert seen == []


def test_concurrent_cancel_vs_match_exactly_one_wins(engine):
    """Race a cancel against a matching order, many times.

    Whichever call takes the engine lock first wins; the outcome must always
    be self-consistent (either filled-and-not-cancellable, or cancelled-and-
    untraded) and invariants must hold.
    """
    for i in range(200):
        sid = f"S{i}"
        engine.submit("AAPL", "SELL", "100", 5, order_id=sid)
        results = {}
        barrier = threading.Barrier(2)

        def do_cancel():
            barrier.wait()
            results["cancel"] = engine.cancel(sid)

        def do_buy():
            barrier.wait()
            results["buy"] = engine.submit("AAPL", "BUY", "100", 5, order_id=f"B{i}")

        threads = [threading.Thread(target=do_cancel), threading.Thread(target=do_buy)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        sell = engine.get_order(sid)
        if results["cancel"].ok:
            assert sell.status is OrderStatus.CANCELLED
            assert results["buy"].trades == []
            engine.cancel(f"B{i}")  # clear the resting buy for the next round
        else:
            assert results["cancel"].status is CancelStatus.ALREADY_FILLED
            assert sell.status is OrderStatus.FILLED
            assert len(results["buy"].trades) == 1
    engine.check_invariants()
