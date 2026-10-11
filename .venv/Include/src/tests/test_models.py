"""Tests for src/models.py: order creation and validation (test areas 1-2)."""

import dataclasses
import unittest
from decimal import Decimal

from src.models import InvalidOrderError, Order, Side, Trade


class TestValidOrderCreation(unittest.TestCase):
    def test_valid_order_fields(self) -> None:
        order = Order("A1", "aapl", "buy", "100.50", 10)
        self.assertEqual(order.order_id, "A1")
        self.assertEqual(order.symbol, "AAPL")          # normalised to upper case
        self.assertIs(order.side, Side.BUY)             # string parsed into the enum
        self.assertEqual(order.price, Decimal("100.50"))
        self.assertEqual(order.quantity, 10)
        self.assertEqual(order.remaining, 10)           # starts fully unfilled
        self.assertFalse(order.is_filled)

    def test_price_accepts_int_decimal_and_str(self) -> None:
        for price in (100, Decimal("100"), "100"):
            with self.subTest(price=price):
                self.assertEqual(Order("A1", "AAPL", Side.SELL, price, 1).price, Decimal("100"))

    def test_price_is_decimal_not_float(self) -> None:
        order = Order("A1", "AAPL", Side.BUY, "0.1", 1)
        self.assertIsInstance(order.price, Decimal)
        self.assertEqual(Decimal("0.1") + Decimal("0.2"), Decimal("0.3"))  # exact


class TestInvalidOrderRejection(unittest.TestCase):
    def test_invalid_prices_rejected(self) -> None:
        for bad in (0, -1, "0", "-5.5", "abc", "NaN", "Infinity", 1.5, None, True):
            with self.subTest(price=bad):
                with self.assertRaises(InvalidOrderError):
                    Order("A1", "AAPL", Side.BUY, bad, 10)

    def test_invalid_quantities_rejected(self) -> None:
        for bad in (0, -3, 1.5, "5", None, True):
            with self.subTest(quantity=bad):
                with self.assertRaises(InvalidOrderError):
                    Order("A1", "AAPL", Side.BUY, 100, bad)

    def test_invalid_symbols_rejected(self) -> None:
        for bad in ("", "   ", "AA1", "A B", "ABCDEFGHIJK", 123, None):
            with self.subTest(symbol=bad):
                with self.assertRaises(InvalidOrderError):
                    Order("A1", bad, Side.BUY, 100, 10)

    def test_invalid_sides_rejected(self) -> None:
        for bad in ("HOLD", None, 1, ""):
            with self.subTest(side=bad):
                with self.assertRaises(InvalidOrderError):
                    Order("A1", "AAPL", bad, 100, 10)

    def test_invalid_order_ids_rejected(self) -> None:
        for bad in ("", "   ", 5, None):
            with self.subTest(order_id=bad):
                with self.assertRaises(InvalidOrderError):
                    Order(bad, "AAPL", Side.BUY, 100, 10)


class TestSideAndTrade(unittest.TestCase):
    def test_side_opposite(self) -> None:
        self.assertIs(Side.BUY.opposite, Side.SELL)
        self.assertIs(Side.SELL.opposite, Side.BUY)

    def test_trade_is_immutable(self) -> None:
        trade = Trade(1, "AAPL", Decimal("100"), 5, "B1", "S1", 0.0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            trade.quantity = 99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()