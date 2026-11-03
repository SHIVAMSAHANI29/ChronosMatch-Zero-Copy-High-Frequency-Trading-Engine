"""Focused correctness checks for the existing ChronosMatch matching engine."""
import unittest
from decimal import Decimal

from src.matching_engine import MatchingEngine


class EngineVerificationTests(unittest.TestCase):
    def setUp(self):
        self.engine = MatchingEngine()

    def test_crossing_buy_matches_resting_sell_at_resting_price(self):
        self.engine.submit("TEST", "SELL", Decimal("100.00"), 10, "SELL-1")
        result = self.engine.submit("TEST", "BUY", Decimal("101.00"), 10, "BUY-1")

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.price, Decimal("100.00"))
        self.assertEqual(trade.quantity, 10)
        self.assertEqual(trade.buy_order_id, "BUY-1")
        self.assertEqual(trade.sell_order_id, "SELL-1")
        self.assertEqual(result.order.remaining, 0)

    def test_partial_fill_leaves_remainder_on_book(self):
        self.engine.submit("TEST", "SELL", Decimal("100.00"), 4, "SELL-2")
        result = self.engine.submit("TEST", "BUY", Decimal("101.00"), 10, "BUY-2")

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].quantity, 4)
        self.assertEqual(result.order.remaining, 6)
        self.assertEqual(result.order.status.value, "PARTIALLY_FILLED")

    def test_non_crossing_orders_do_not_trade(self):
        self.engine.submit("TEST", "SELL", Decimal("105.00"), 5, "SELL-3")
        result = self.engine.submit("TEST", "BUY", Decimal("100.00"), 5, "BUY-3")
        self.assertEqual(result.trades, [])
        self.assertEqual(result.order.remaining, 5)

    def test_different_symbols_do_not_match(self):
        self.engine.submit("AAA", "SELL", Decimal("10.00"), 5, "SELL-4")
        result = self.engine.submit("BBB", "BUY", Decimal("11.00"), 5, "BUY-4")
        self.assertEqual(result.trades, [])

    def test_sell_incoming_matches_resting_buy_at_resting_price(self):
        self.engine.submit("TEST", "BUY", Decimal("100.00"), 3, "BUY-5")
        result = self.engine.submit("TEST", "SELL", Decimal("99.00"), 3, "SELL-5")
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].price, Decimal("100.00"))
        self.assertEqual(result.trades[0].quantity, 3)


if __name__ == "__main__":
    unittest.main()
