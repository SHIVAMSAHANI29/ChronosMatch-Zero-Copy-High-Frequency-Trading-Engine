import random
from decimal import Decimal

import pytest

from src.matching_engine import EventType, MatchingEngine
from src.models import DuplicateOrderError, OrderStatus, OrderValidationError, Side
from tests.conftest import FakeClock


def D(x):
    return Decimal(str(x))


class TestBasicMatching:
    def test_no_match_rests_in_book(self, engine):
        res = engine.submit("AAPL", "BUY", "100", 10)
        assert res.trades == []
        assert res.order.status is OrderStatus.NEW
        assert engine.order_book_snapshot("AAPL")["bids"] == [
            {"price": "100.0000", "quantity": 10, "orders": 1}
        ]

    def test_equal_price_full_match(self, engine):
        engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
        res = engine.submit("AAPL", "BUY", "100", 10, order_id="B1")
        assert len(res.trades) == 1
        t = res.trades[0]
        assert (t.price, t.quantity, t.buy_order_id, t.sell_order_id) == (D(100), 10, "B1", "S1")
        assert engine.get_order("S1").status is OrderStatus.FILLED
        assert res.order.status is OrderStatus.FILLED
        assert engine.stats()["active_orders"] == 0

    def test_non_crossing_orders_do_not_trade(self, engine):
        engine.submit("AAPL", "SELL", "101", 10)
        res = engine.submit("AAPL", "BUY", "100", 10)
        assert res.trades == []
        assert engine.stats()["active_orders"] == 2
        engine.check_invariants()

    def test_incoming_buy_trades_at_resting_sell_price(self, engine):
        engine.submit("AAPL", "SELL", "100", 10)
        res = engine.submit("AAPL", "BUY", "105", 10)
        assert res.trades[0].price == D(100)

    def test_incoming_sell_trades_at_resting_buy_price(self, engine):
        engine.submit("AAPL", "BUY", "105", 10)
        res = engine.submit("AAPL", "SELL", "100", 10)
        assert res.trades[0].price == D(105)


class TestPartialAndMultipleFills:
    def test_incoming_larger_than_resting(self, engine):
        engine.submit("AAPL", "SELL", "100", 4, order_id="S1")
        res = engine.submit("AAPL", "BUY", "100", 10, order_id="B1")
        assert [t.quantity for t in res.trades] == [4]
        assert res.order.remaining == 6
        assert res.order.status is OrderStatus.PARTIALLY_FILLED
        # remainder rests on the bid side
        assert engine.order_book_snapshot("AAPL")["bids"][0]["quantity"] == 6
        assert engine.order_book_snapshot("AAPL")["asks"] == []

    def test_incoming_smaller_than_resting(self, engine):
        engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
        res = engine.submit("AAPL", "BUY", "100", 3)
        assert res.order.status is OrderStatus.FILLED
        s1 = engine.get_order("S1")
        assert (s1.remaining, s1.status) == (7, OrderStatus.PARTIALLY_FILLED)
        assert engine.order_book_snapshot("AAPL")["asks"][0]["quantity"] == 7

    def test_sweeps_multiple_levels_in_price_order(self, engine):
        engine.submit("AAPL", "SELL", "102", 5, order_id="S102")
        engine.submit("AAPL", "SELL", "100", 5, order_id="S100")
        engine.submit("AAPL", "SELL", "101", 5, order_id="S101")
        res = engine.submit("AAPL", "BUY", "102", 12)
        assert [(t.sell_order_id, t.price, t.quantity) for t in res.trades] == [
            ("S100", D(100), 5), ("S101", D(101), 5), ("S102", D(102), 2),
        ]
        assert res.order.status is OrderStatus.FILLED
        assert engine.get_order("S102").remaining == 3
        engine.check_invariants()

    def test_stops_at_limit_price(self, engine):
        engine.submit("AAPL", "SELL", "100", 5)
        engine.submit("AAPL", "SELL", "103", 5)
        res = engine.submit("AAPL", "BUY", "101", 20)
        assert len(res.trades) == 1
        assert res.order.remaining == 15
        assert engine.order_book_snapshot("AAPL")["bids"][0]["price"] == "101.0000"

    def test_incoming_sell_sweeps_bids_highest_first(self, engine):
        engine.submit("AAPL", "BUY", "99", 5, order_id="B99")
        engine.submit("AAPL", "BUY", "101", 5, order_id="B101")
        engine.submit("AAPL", "BUY", "100", 5, order_id="B100")
        res = engine.submit("AAPL", "SELL", "99", 12)
        assert [t.buy_order_id for t in res.trades] == ["B101", "B100", "B99"]
        assert [t.quantity for t in res.trades] == [5, 5, 2]


class TestPriority:
    def test_price_priority_beats_arrival_time(self, engine):
        engine.submit("AAPL", "SELL", "101", 5, order_id="early-expensive")
        engine.submit("AAPL", "SELL", "100", 5, order_id="late-cheap")
        res = engine.submit("AAPL", "BUY", "101", 5)
        assert res.trades[0].sell_order_id == "late-cheap"

    def test_time_priority_at_equal_price(self, engine):
        for i in (1, 2, 3):
            engine.submit("AAPL", "SELL", "100", 5, order_id=f"S{i}")
        res = engine.submit("AAPL", "BUY", "100", 10)
        assert [t.sell_order_id for t in res.trades] == ["S1", "S2"]
        assert engine.get_order("S3").status is OrderStatus.NEW

    def test_partially_filled_order_keeps_its_place_in_queue(self, engine):
        engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
        engine.submit("AAPL", "SELL", "100", 10, order_id="S2")
        engine.submit("AAPL", "BUY", "100", 4)
        res = engine.submit("AAPL", "BUY", "100", 8)
        assert [(t.sell_order_id, t.quantity) for t in res.trades] == [("S1", 6), ("S2", 2)]


class TestSymbols:
    def test_symbols_are_isolated(self, engine):
        engine.submit("AAPL", "SELL", "100", 10)
        res = engine.submit("MSFT", "BUY", "100", 10)
        assert res.trades == []
        assert engine.symbols() == ["AAPL", "MSFT"]
        assert engine.order_book_snapshot("AAPL")["asks"][0]["quantity"] == 10
        assert engine.order_book_snapshot("MSFT")["bids"][0]["quantity"] == 10

    def test_symbol_is_case_insensitive(self, engine):
        engine.submit("aapl", "SELL", "100", 10)
        res = engine.submit("AAPL", "BUY", "100", 10)
        assert len(res.trades) == 1

    def test_unknown_symbol_snapshot_is_empty(self, engine):
        assert engine.order_book_snapshot("NOPE") == {"symbol": "NOPE", "bids": [], "asks": []}


class TestValidationAndIds:
    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(symbol="", side="BUY", price="1", quantity=1),
            dict(symbol="AAPL", side="HOLD", price="1", quantity=1),
            dict(symbol="AAPL", side="BUY", price="0", quantity=1),
            dict(symbol="AAPL", side="BUY", price=1.5, quantity=1),
            dict(symbol="AAPL", side="BUY", price="1", quantity=0),
            dict(symbol="AAPL", side="BUY", price="1", quantity=-3),
            dict(symbol="AAPL", side="BUY", price="1", quantity=2.5),
            dict(symbol="AAPL", side="BUY", price="1", quantity=1, order_id="bad id"),
        ],
    )
    def test_invalid_orders_rejected_without_side_effects(self, engine, kwargs):
        with pytest.raises(OrderValidationError):
            engine.submit(**kwargs)
        stats = engine.stats()
        assert stats["orders_accepted"] == 0
        assert stats["orders_rejected"] == 1
        # a rejected order must not burn a sequence number
        assert engine.submit("AAPL", "BUY", "1", 1).order.sequence == 1

    def test_duplicate_id_rejected(self, engine):
        engine.submit("AAPL", "BUY", "100", 5, order_id="X")
        with pytest.raises(DuplicateOrderError):
            engine.submit("MSFT", "SELL", "50", 5, order_id="X")
        assert engine.stats()["orders_accepted"] == 1

    def test_duplicate_id_rejected_even_after_fill_or_cancel(self, engine):
        engine.submit("AAPL", "SELL", "100", 5, order_id="S")
        engine.submit("AAPL", "BUY", "100", 5, order_id="B")
        with pytest.raises(DuplicateOrderError):
            engine.submit("AAPL", "BUY", "100", 5, order_id="B")
        engine.submit("AAPL", "BUY", "90", 5, order_id="C")
        engine.cancel("C")
        with pytest.raises(DuplicateOrderError):
            engine.submit("AAPL", "BUY", "90", 5, order_id="C")

    def test_generated_ids_are_unique_and_skip_user_ids(self, engine):
        engine.submit("AAPL", "BUY", "1", 1, order_id="ORD-00000001")
        a = engine.submit("AAPL", "BUY", "1", 1).order.order_id
        b = engine.submit("AAPL", "BUY", "1", 1).order.order_id
        assert a != b != "ORD-00000001"
        assert a != "ORD-00000001"

    def test_sequence_numbers_strictly_increase(self, engine):
        seqs = [engine.submit("AAPL", "BUY", "1", 1).order.sequence for _ in range(20)]
        assert seqs == list(range(1, 21))


class TestTradeRecords:
    def test_trade_fields_and_sequence(self, engine):
        engine.submit("AAPL", "SELL", "100", 5, order_id="S1")
        engine.submit("AAPL", "SELL", "100", 5, order_id="S2")
        res = engine.submit("AAPL", "BUY", "100", 10, order_id="B1")
        t1, t2 = res.trades
        assert (t1.trade_id, t1.sequence) == ("TRD-00000001", 1)
        assert (t2.trade_id, t2.sequence) == ("TRD-00000002", 2)
        assert t1.timestamp < t2.timestamp
        assert t1.symbol == "AAPL"

    def test_recent_trades_newest_first_and_filtered(self, engine):
        for sym in ("AAPL", "MSFT", "AAPL"):
            engine.submit(sym, "SELL", "10", 1)
            engine.submit(sym, "BUY", "10", 1)
        assert [t.sequence for t in engine.recent_trades()] == [3, 2, 1]
        assert [t.sequence for t in engine.recent_trades(symbol="AAPL")] == [3, 1]
        assert len(engine.recent_trades(limit=2)) == 2

    def test_stats_totals(self, engine):
        engine.submit("AAPL", "SELL", "10", 7)
        engine.submit("AAPL", "BUY", "10", 5)
        s = engine.stats()
        assert (s["trades"], s["traded_quantity"], s["active_orders"]) == (1, 5, 1)
        assert s["active_sell_orders"] == 1 and s["active_buy_orders"] == 0


class TestQueries:
    def test_get_orders_filters(self, engine):
        engine.submit("AAPL", "BUY", "10", 1, order_id="a")
        engine.submit("AAPL", "SELL", "20", 1, order_id="b")
        engine.submit("MSFT", "BUY", "10", 1, order_id="c")
        engine.submit("MSFT", "SELL", "10", 1, order_id="d")  # fills c and d
        assert [o.order_id for o in engine.get_orders()] == ["a", "b"]
        assert [o.order_id for o in engine.get_orders(symbol="aapl", side="buy")] == ["a"]
        assert [o.order_id for o in engine.get_orders(active_only=False)] == ["a", "b", "c", "d"]

    def test_get_order_unknown(self, engine):
        assert engine.get_order("nope") is None


class TestEvents:
    def test_event_sequence_for_a_full_match(self, engine):
        engine.submit("AAPL", "SELL", "100", 5, order_id="S1")
        seen = []
        engine.subscribe(seen.append)
        engine.submit("AAPL", "BUY", "100", 5, order_id="B1")
        kinds = [e.type for e in seen]
        assert kinds == [
            EventType.ORDER_ACCEPTED,
            EventType.TRADE_EXECUTED,
            EventType.ORDER_FILLED,   # resting S1
            EventType.ORDER_FILLED,   # incoming B1
            EventType.BOOK_UPDATED,
        ]
        d = seen[1].to_dict()
        assert set(d) == {"type", "symbol", "timestamp", "payload"}
        assert d["payload"]["quantity"] == 5

    def test_partial_fill_event(self, engine):
        engine.submit("AAPL", "SELL", "100", 10, order_id="S1")
        seen = []
        engine.subscribe(seen.append)
        engine.submit("AAPL", "BUY", "100", 4)
        assert EventType.ORDER_PARTIALLY_FILLED in [e.type for e in seen]

    def test_failing_listener_does_not_break_matching(self, engine):
        def boom(_):
            raise RuntimeError("listener bug")

        engine.subscribe(boom)
        engine.submit("AAPL", "SELL", "100", 5)
        res = engine.submit("AAPL", "BUY", "100", 5)
        assert len(res.trades) == 1

    def test_unsubscribe(self, engine):
        seen = []
        engine.subscribe(seen.append)
        engine.unsubscribe(seen.append)
        engine.submit("AAPL", "BUY", "1", 1)
        # bound-method objects compare equal, so the listener is removed
        assert seen == []


class TestDeterminismAndInvariants:
    @staticmethod
    def run_stream(seed, n=600):
        rng = random.Random(seed)
        eng = MatchingEngine(clock=FakeClock())
        live: list[str] = []
        for i in range(n):
            if live and rng.random() < 0.15:
                eng.cancel(live.pop(rng.randrange(len(live))))
                continue
            res = eng.submit(
                rng.choice(["AAPL", "MSFT", "GOOG"]),
                rng.choice(["BUY", "SELL"]),
                D(rng.randint(95, 105)),
                rng.randint(1, 50),
                order_id=f"O{i}",
            )
            live.append(res.order.order_id)
        return eng

    def test_same_input_gives_identical_trades(self):
        a, b = self.run_stream(7), self.run_stream(7)
        assert [t.to_dict() for t in a.trades] == [t.to_dict() for t in b.trades]
        assert len(a.trades) > 0

    def test_different_input_gives_different_trades(self):
        assert [t.to_dict() for t in self.run_stream(1).trades] != [
            t.to_dict() for t in self.run_stream(2).trades
        ]

    @pytest.mark.parametrize("seed", range(5))
    def test_invariants_hold_on_random_streams(self, seed):
        self.run_stream(seed).check_invariants()

    def test_large_batch(self):
        eng = MatchingEngine(clock=FakeClock())
        rng = random.Random(42)
        for _ in range(20_000):
            eng.submit(
                "AAPL", rng.choice(["BUY", "SELL"]), D(rng.randint(90, 110)), rng.randint(1, 100)
            )
        eng.check_invariants()
        s = eng.stats()
        assert s["orders_accepted"] == 20_000
        assert s["trades"] > 0
        # conservation: total bought == total sold == traded quantity
        bought = sum(o.filled_quantity for o in eng.get_orders(side="BUY", active_only=False))
        sold = sum(o.filled_quantity for o in eng.get_orders(side="SELL", active_only=False))
        assert bought == sold == s["traded_quantity"]

    def test_book_never_crossed_after_every_submit(self):
        eng = MatchingEngine(clock=FakeClock())
        rng = random.Random(3)
        for _ in range(500):
            eng.submit("AAPL", rng.choice(["BUY", "SELL"]), D(rng.randint(98, 102)), rng.randint(1, 20))
            book = eng.get_book("AAPL")
            bid, ask = book.best_bid(), book.best_ask()
            assert bid is None or ask is None or bid < ask
