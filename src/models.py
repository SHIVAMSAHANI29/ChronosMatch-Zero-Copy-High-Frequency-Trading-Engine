"""Order and trade models, plus input validation.

Design notes
------------
* Prices are :class:`decimal.Decimal`, never ``float``. Floats are rejected
  outright because ``0.1 + 0.2 != 0.3`` in binary floating point.
* Every :class:`Order` validates itself in ``__post_init__``, so an invalid
  order object can never exist (and therefore can never reach the book).
* Orders are *mutable* (remaining quantity and status change as they fill);
  trades are *immutable* records.
* ``slots=True`` removes the per-instance ``__dict__``, which saves memory per
  order (measured later in the optimization phase).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from . import config

__all__ = [
    "Side",
    "OrderStatus",
    "Order",
    "Trade",
    "OrderValidationError",
    "DuplicateOrderError",
    "validate_symbol",
    "validate_side",
    "validate_price",
    "validate_quantity",
    "validate_order_id",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class OrderValidationError(ValueError):
    """An order field is missing, malformed, or out of range."""


class DuplicateOrderError(ValueError):
    """An order ID has already been used."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
_SYMBOL_RE = re.compile(config.SYMBOL_PATTERN)
_ORDER_ID_RE = re.compile(config.ORDER_ID_PATTERN)
# Plain decimal text only: digits with an optional fractional part. This
# rejects "1e2", "+5", "NaN", "Infinity", "1_000" and similar surprises that
# Decimal() would otherwise accept.
_PRICE_TEXT_RE = re.compile(r"\d+(\.\d+)?")
_TICK = Decimal(1).scaleb(-config.PRICE_DECIMAL_PLACES)


def validate_symbol(symbol: Any) -> str:
    """Return the normalised (stripped, upper-case) symbol or raise."""
    if not isinstance(symbol, str):
        raise OrderValidationError("symbol must be a string")
    cleaned = symbol.strip().upper()
    if not _SYMBOL_RE.fullmatch(cleaned):
        raise OrderValidationError(
            "symbol must be 1-10 characters, letters and digits only"
        )
    return cleaned


def validate_side(side: Any) -> Side:
    """Return a :class:`Side` or raise."""
    if isinstance(side, Side):
        return side
    if isinstance(side, str):
        try:
            return Side(side.strip().upper())
        except ValueError:
            pass
    raise OrderValidationError("side must be BUY or SELL")


def validate_price(price: Any) -> Decimal:
    """Return the price as a Decimal at the tick size, or raise.

    Accepts ``Decimal``, ``int`` and plain-decimal ``str``. Rejects ``float``
    and ``bool`` on purpose.
    """
    if isinstance(price, bool) or isinstance(price, float):
        raise OrderValidationError(
            "price must be a Decimal, int or decimal string (floats are not allowed)"
        )
    if isinstance(price, Decimal):
        value = price
    elif isinstance(price, int):
        value = Decimal(price)
    elif isinstance(price, str):
        text = price.strip()
        if not _PRICE_TEXT_RE.fullmatch(text):
            raise OrderValidationError("price is not a valid decimal number")
        try:
            value = Decimal(text)
        except InvalidOperation:  # pragma: no cover - regex already guards this
            raise OrderValidationError("price is not a valid decimal number") from None
    else:
        raise OrderValidationError("price must be a Decimal, int or decimal string")

    if not value.is_finite():
        raise OrderValidationError("price must be finite")
    if value <= 0:
        raise OrderValidationError("price must be greater than zero")
    if value > config.MAX_PRICE:
        raise OrderValidationError(f"price must not exceed {config.MAX_PRICE}")
    quantized = value.quantize(_TICK)
    if quantized != value:
        raise OrderValidationError(
            f"price must have at most {config.PRICE_DECIMAL_PLACES} decimal places"
        )
    return quantized


def validate_quantity(quantity: Any) -> int:
    """Return a positive integer quantity or raise."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise OrderValidationError("quantity must be an integer")
    if quantity <= 0:
        raise OrderValidationError("quantity must be greater than zero")
    if quantity > config.MAX_QUANTITY:
        raise OrderValidationError(f"quantity must not exceed {config.MAX_QUANTITY}")
    return quantity


def validate_order_id(order_id: Any) -> str:
    """Return a valid order ID or raise."""
    if not isinstance(order_id, str) or not _ORDER_ID_RE.fullmatch(order_id):
        raise OrderValidationError(
            "order_id must be 1-64 characters: letters, digits, '_', '-' or '.'"
        )
    return order_id


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Order:
    """A limit order.

    ``remaining`` defaults to ``quantity``. ``sequence`` is assigned by the
    matching engine and increases by one for every accepted order; it is the
    tie-breaker for time priority.
    """

    order_id: str
    symbol: str
    side: Side
    price: Decimal
    quantity: int
    timestamp: datetime
    sequence: int
    remaining: int | None = None
    status: OrderStatus = OrderStatus.NEW

    def __post_init__(self) -> None:
        self.order_id = validate_order_id(self.order_id)
        self.symbol = validate_symbol(self.symbol)
        self.side = validate_side(self.side)
        self.price = validate_price(self.price)
        self.quantity = validate_quantity(self.quantity)
        if not isinstance(self.timestamp, datetime):
            raise OrderValidationError("timestamp must be a datetime")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise OrderValidationError("sequence must be a positive integer")
        if self.remaining is None:
            self.remaining = self.quantity
        elif (
            isinstance(self.remaining, bool)
            or not isinstance(self.remaining, int)
            or not 0 <= self.remaining <= self.quantity
        ):
            raise OrderValidationError("remaining must be between 0 and quantity")
        if not isinstance(self.status, OrderStatus):
            self.status = OrderStatus(self.status)

    # -- state ---------------------------------------------------------
    @property
    def is_active(self) -> bool:
        """True while the order can still trade or be cancelled."""
        return self.status is OrderStatus.NEW or self.status is OrderStatus.PARTIALLY_FILLED

    @property
    def filled_quantity(self) -> int:
        return self.quantity - self.remaining  # type: ignore[operator]

    def fill(self, quantity: int) -> None:
        """Execute *quantity* shares against this order and update its status."""
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if not self.is_active:
            raise ValueError(f"cannot fill an order that is {self.status}")
        if quantity > self.remaining:  # type: ignore[operator]
            raise ValueError("fill quantity exceeds remaining quantity")
        self.remaining -= quantity  # type: ignore[operator]
        self.status = OrderStatus.FILLED if self.remaining == 0 else OrderStatus.PARTIALLY_FILLED

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly snapshot. Price is a string to keep it exact."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "price": str(self.price),
            "quantity": self.quantity,
            "remaining": self.remaining,
            "filled": self.filled_quantity,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Trade:
    """An executed trade between one buy order and one sell order."""

    trade_id: str
    symbol: str
    price: Decimal
    quantity: int
    buy_order_id: str
    sell_order_id: str
    timestamp: datetime
    sequence: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("trade quantity must be positive")
        if self.price <= 0:
            raise ValueError("trade price must be positive")
        if self.buy_order_id == self.sell_order_id:
            raise ValueError("a trade needs two different orders")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "price": str(self.price),
            "quantity": self.quantity,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
        }
