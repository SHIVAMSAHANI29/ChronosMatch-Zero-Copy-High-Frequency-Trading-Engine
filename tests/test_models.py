from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.models import (
    Order,
    OrderStatus,
    OrderValidationError,
    Side,
    Trade,
    validate_order_id,
    validate_price,
    validate_quantity,
    validate_side,
    validate_symbol,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_order(**overrides):
    fields = dict(
        order_id="A1", symbol="AAPL", side=Side.BUY, price="100.50",
        quantity=10, timestamp=NOW, sequence=1,
    )
    fields.update(overrides)
    return Order(**fields)


class TestSymbol:
    def test_normalises_case_and_whitespace(self):
        assert validate_symbol("  aapl ") == "AAPL"

    @pytest.mark.parametrize("bad", ["", "   ", "TOOLONGSYMBOL", "AA PL", "AA-PL", "$AAPL", None, 5])
    def test_rejects_bad_symbols(self, bad):
        with pytest.raises(OrderValidationError):
            validate_symbol(bad)


class TestSide:
    def test_accepts_strings_any_case(self):
        assert validate_side("buy") is Side.BUY
        assert validate_side(" SELL ") is Side.SELL

    @pytest.mark.parametrize("bad", ["HOLD", "", None, 1])
    def test_rejects_bad_sides(self, bad):
        with pytest.raises(OrderValidationError):
            validate_side(bad)


class TestPrice:
    def test_accepts_decimal_int_and_string(self):
        assert validate_price(Decimal("10.5")) == Decimal("10.5000")
        assert validate_price(10) == Decimal("10")
        assert validate_price("0.0001") == Decimal("0.0001")

    def test_float_rejected(self):
        with pytest.raises(OrderValidationError, match="float"):
            validate_price(10.5)

    @pytest.mark.parametrize(
        "bad",
        ["0", "-1", "1e2", "+5", "NaN", "Infinity", "1_000", "abc", "", "1.00001",
         "1000000.0001", True, None, Decimal("NaN"), Decimal("Infinity"), Decimal("-5"), 0],
    )
    def test_rejects_bad_prices(self, bad):
        with pytest.raises(OrderValidationError):
            validate_price(bad)

    def test_max_price_allowed(self):
        assert validate_price("1000000") == Decimal("1000000")


class TestQuantity:
    def test_accepts_positive_int(self):
        assert validate_quantity(1) == 1

    @pytest.mark.parametrize("bad", [0, -5, 1.5, "10", True, None, 1_000_000_001])
    def test_rejects_bad_quantities(self, bad):
        with pytest.raises(OrderValidationError):
            validate_quantity(bad)


class TestOrderId:
    def test_accepts_valid(self):
        assert validate_order_id("abc-1_2.3") == "abc-1_2.3"

    @pytest.mark.parametrize("bad", ["", "a b", "x" * 65, "a/b", None, 5])
    def test_rejects_invalid(self, bad):
        with pytest.raises(OrderValidationError):
            validate_order_id(bad)


class TestOrder:
    def test_defaults(self):
        order = make_order()
        assert order.remaining == 10
        assert order.status is OrderStatus.NEW
        assert order.is_active
        assert order.filled_quantity == 0

    def test_normalises_fields(self):
        order = make_order(symbol="msft", side="sell", price=5)
        assert (order.symbol, order.side, order.price) == ("MSFT", Side.SELL, Decimal("5.0000"))

    @pytest.mark.parametrize(
        "override",
        [
            {"quantity": 0}, {"price": "0"}, {"price": 1.5}, {"symbol": ""},
            {"side": "HOLD"}, {"order_id": ""}, {"sequence": 0}, {"timestamp": "now"},
            {"remaining": 11}, {"remaining": -1},
        ],
    )
    def test_invalid_orders_cannot_be_constructed(self, override):
        with pytest.raises(OrderValidationError):
            make_order(**override)

    def test_partial_then_full_fill(self):
        order = make_order()
        order.fill(4)
        assert (order.remaining, order.status) == (6, OrderStatus.PARTIALLY_FILLED)
        order.fill(6)
        assert (order.remaining, order.status) == (0, OrderStatus.FILLED)
        assert not order.is_active

    def test_fill_guards(self):
        order = make_order()
        with pytest.raises(ValueError):
            order.fill(0)
        with pytest.raises(ValueError):
            order.fill(11)
        order.fill(10)
        with pytest.raises(ValueError):
            order.fill(1)

    def test_to_dict_keeps_price_exact(self):
        data = make_order(price="0.1").to_dict()
        assert data["price"] == "0.1000"
        assert data["status"] == "NEW"


class TestTrade:
    def make(self, **overrides):
        fields = dict(
            trade_id="T1", symbol="AAPL", price=Decimal("10"), quantity=5,
            buy_order_id="B", sell_order_id="S", timestamp=NOW, sequence=1,
        )
        fields.update(overrides)
        return Trade(**fields)

    def test_valid_trade_is_immutable(self):
        trade = self.make()
        with pytest.raises(AttributeError):
            trade.quantity = 9  # type: ignore[misc]
        assert trade.to_dict()["price"] == "10"

    @pytest.mark.parametrize(
        "override", [{"quantity": 0}, {"price": Decimal("0")}, {"sell_order_id": "B"}]
    )
    def test_invalid_trades_rejected(self, override):
        with pytest.raises(ValueError):
            self.make(**override)
