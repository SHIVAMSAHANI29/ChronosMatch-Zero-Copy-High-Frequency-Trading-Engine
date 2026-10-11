"""Tests for the matching engine (test areas 3-12)."""

import unittest
from decimal import Decimal

from src.matching_engine import MatchingEngine
from src.models import DuplicateOrderError, InvalidOrderError, Order, Side


def make(order_id: str, side: Side, price: int, quantity: int, symbol: str = "AAPL") -> Order:
    """Small helper to keep the tests short."""
    return Order(order_id, symbol, side, price, quantity)


class TestMatchingBasics(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MatchingEngine()

    def test_match_at_equal_prices(self) -> None:                      # area 3
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        trades = self.engine.submit_order(make("S1", Side.SELL, 100, 10))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].quantity, 10)
        self.assertEqual(trades[0].price, Decimal("100"))
        self.assertEqual(trades[0].buy_order_id, "B1")
        self.assertEqual(trades[0].sell_order_id, "S1")
        self.assertEqual(trades[0].symbol, "AAPL")

    def test_no_trade_when_buy_below_sell(self) -> None:               # area 4
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        trades = self.engine.submit_order(make("S1", Side.SELL, 101, 10))
        self.assertEqual(trades, [])
        self.assertEqual(self.engine.trade_count, 0)
        self.assertEqual(len(self.engine.open_orders("AAPL", Side.BUY)), 1)
        self.assertEqual(len(self.engine.open_orders("AAPL", Side.SELL)), 1)

    def test_partial_fill_of_resting_order(self) -> None:              # area 5
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        trades = self.engine.submit_order(make("S1", Side.SELL, 100, 4))
        self.assertEqual(trades[0].quantity, 4)
        buys = self.engine.open_orders("AAPL", Side.BUY)
        self.assertEqual([(o.order_id, o.remaining) for o in buys], [("B1", 6)])
        self.assertEqual(self.engine.open_orders("AAPL", Side.SELL), [])

    def test_partial_fill_of_incoming_order_rests(self) -> None:       # area 5
        self.engine.submit_order(make("S1", Side.SELL, 100, 4))
        trades = self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        self.assertEqual(trades[0].quantity, 4)
        buys = self.engine.open_orders("AAPL", Side.BUY)
        self.assertEqual([(o.order_id, o.remaining) for o in buys], [("B1", 6)])
        self.assertEqual(self.engine.open_orders("AAPL", Side.SELL), [])

    def test_different_symbols_do_not_match(self) -> None:             # area 8
        self.engine.submit_order(make("B1", Side.BUY, 100, 10, "AAPL"))
        trades = self.engine.submit_order(make("S1", Side.SELL, 100, 10, "MSFT"))
        self.assertEqual(trades, [])
        self.assertEqual(len(self.engine.open_orders("AAPL", Side.BUY)), 1)
        self.assertEqual(len(self.engine.open_orders("MSFT", Side.SELL)), 1)

    def test_fully_filled_orders_removed(self) -> None:                # area 9
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        self.engine.submit_order(make("S1", Side.SELL, 100, 10))
        self.assertEqual(self.engine.open_orders("AAPL", Side.BUY), [])
        self.assertEqual(self.engine.open_orders("AAPL", Side.SELL), [])


class TestPriority(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MatchingEngine()

    def test_multiple_orders_same_price_time_priority(self) -> None:   # areas 6, 7
        self.engine.submit_order(make("S1", Side.SELL, 100, 5))
        self.engine.submit_order(make("S2", Side.SELL, 100, 5))
        trades = self.engine.submit_order(make("B1", Side.BUY, 100, 7))
        self.assertEqual([(t.sell_order_id, t.quantity) for t in trades], [("S1", 5), ("S2", 2)])
        sells = self.engine.open_orders("AAPL", Side.SELL)
        self.assertEqual([(o.order_id, o.remaining) for o in sells], [("S2", 3)])

    def test_lowest_sell_price_matched_first(self) -> None:            # area 7
        self.engine.submit_order(make("S1", Side.SELL, 102, 1))
        self.engine.submit_order(make("S2", Side.SELL, 101, 1))
        self.engine.submit_order(make("S3", Side.SELL, 103, 1))
        trades = self.engine.submit_order(make("B1", Side.BUY, 103, 1))
        self.assertEqual(trades[0].sell_order_id, "S2")
        self.assertEqual(trades[0].price, Decimal("101"))

    def test_highest_buy_price_matched_first(self) -> None:            # area 7
        self.engine.submit_order(make("B1", Side.BUY, 100, 1))
        self.engine.submit_order(make("B2", Side.BUY, 101, 1))
        trades = self.engine.submit_order(make("S1", Side.SELL, 99, 1))
        self.assertEqual(trades[0].buy_order_id, "B2")

    def test_open_orders_listed_in_priority_order(self) -> None:       # area 7
        self.engine.submit_order(make("B1", Side.BUY, 100, 1))
        self.engine.submit_order(make("B2", Side.BUY, 101, 1))
        self.engine.submit_order(make("B3", Side.BUY, 100, 1))
        buys = self.engine.open_orders("AAPL", Side.BUY)
        self.assertEqual([o.order_id for o in buys], ["B2", "B1", "B3"])

    def test_execution_price_is_resting_price(self) -> None:
        self.engine.submit_order(make("B1", Side.BUY, 100, 1))
        trades = self.engine.submit_order(make("S1", Side.SELL, 99, 1))
        self.assertEqual(trades[0].price, Decimal("100"))   # resting buy sets price

        self.engine.submit_order(make("S2", Side.SELL, 99, 1))
        trades = self.engine.submit_order(make("B2", Side.BUY, 100, 1))
        self.assertEqual(trades[0].price, Decimal("99"))    # resting sell sets price

    def test_sequence_numbers_increase(self) -> None:
        a, b = make("B1", Side.BUY, 100, 1), make("B2", Side.BUY, 100, 1)
        self.engine.submit_order(a)
        self.engine.submit_order(b)
        self.assertLess(a.sequence, b.sequence)


class TestMultipleTrades(unittest.TestCase):
    def test_sweep_across_price_levels(self) -> None:                  # areas 10, 12
        engine = MatchingEngine()
        engine.submit_order(make("S1", Side.SELL, 100, 3))
        engine.submit_order(make("S2", Side.SELL, 101, 4))
        engine.submit_order(make("S3", Side.SELL, 102, 5))

        trades = engine.submit_order(make("B1", Side.BUY, 102, 10))

        self.assertEqual(
            [(t.sell_order_id, t.quantity, t.price) for t in trades],
            [("S1", 3, Decimal("100")), ("S2", 4, Decimal("101")), ("S3", 3, Decimal("102"))],
        )
        self.assertEqual([t.trade_id for t in trades], [1, 2, 3])
        self.assertEqual(engine.trade_count, 3)
        self.assertEqual(engine.total_traded_quantity, 10)
        self.assertEqual(engine.total_traded_value(), Decimal("1010"))   # 300 + 404 + 306
        self.assertEqual(engine.open_orders("AAPL", Side.BUY), [])
        sells = engine.open_orders("AAPL", Side.SELL)
        self.assertEqual([(o.order_id, o.remaining) for o in sells], [("S3", 2)])

    def test_leftover_of_sweep_rests_in_book(self) -> None:            # area 10
        engine = MatchingEngine()
        engine.submit_order(make("S1", Side.SELL, 100, 3))
        engine.submit_order(make("S2", Side.SELL, 101, 4))
        engine.submit_order(make("B1", Side.BUY, 101, 10))
        self.assertEqual(engine.open_orders("AAPL", Side.SELL), [])
        buys = engine.open_orders("AAPL", Side.BUY)
        self.assertEqual([(o.order_id, o.remaining) for o in buys], [("B1", 3)])

    def test_incoming_sell_records_correct_buyer_and_seller(self) -> None:
        engine = MatchingEngine()
        engine.submit_order(make("B1", Side.BUY, 100, 2))
        trades = engine.submit_order(make("S1", Side.SELL, 100, 2))
        self.assertEqual((trades[0].buy_order_id, trades[0].sell_order_id), ("B1", "S1"))


class TestRejection(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MatchingEngine()

    def test_duplicate_order_id_rejected(self) -> None:                # area 11
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        with self.assertRaises(DuplicateOrderError):
            self.engine.submit_order(make("B1", Side.BUY, 100, 5))
        buys = self.engine.open_orders("AAPL", Side.BUY)
        self.assertEqual([(o.order_id, o.remaining) for o in buys], [("B1", 10)])

    def test_duplicate_id_rejected_even_after_order_filled(self) -> None:   # area 11
        self.engine.submit_order(make("B1", Side.BUY, 100, 10))
        self.engine.submit_order(make("S1", Side.SELL, 100, 10))
        with self.assertRaises(DuplicateOrderError):
            self.engine.submit_order(make("B1", Side.BUY, 100, 1))
        self.assertEqual(self.engine.trade_count, 1)

    def test_order_changed_after_creation_is_rejected(self) -> None:
        order = make("B1", Side.BUY, 100, 10)
        order.price = Decimal("-1")      # tampering after construction
        with self.assertRaises(InvalidOrderError):
            self.engine.submit_order(order)
        # A rejected order must leave no trace: its ID is still free.
        order.price = Decimal("100")
        self.engine.submit_order(order)
        self.assertEqual(len(self.engine.open_orders("AAPL", Side.BUY)), 1)

    def test_non_order_object_rejected(self) -> None:
        with self.assertRaises(InvalidOrderError):
            self.engine.submit_order("not an order")  # type: ignore[arg-type]

    def test_partly_filled_order_cannot_be_submitted(self) -> None:
        order = make("B1", Side.BUY, 100, 10)
        order.remaining = 5
        with self.assertRaises(InvalidOrderError):
            self.engine.submit_order(order)


if __name__ == "__main__":
    unittest.main()