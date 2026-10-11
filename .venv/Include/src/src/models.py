"""Data models for ChronosMatch: Side, Order, Trade, and error types.

This module only describes WHAT an order and a trade are, and validates them.
It contains no matching logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

# Prices may be passed as Decimal, int, or str. Floats are rejected on purpose
# because they cannot represent many decimal values exactly (0.1 + 0.2 != 0.3).
PriceLike = Decimal | int | str

# Assumption: symbols are 1-10 uppercase letters (e.g. AAPL, MSFT).
_SYMBOL_PATTERN = re.compile(r"[A-Z]{1,10}")


class InvalidOrderError(ValueError):
    """Raised when an order fails validation."""


class DuplicateOrderError(InvalidOrderError):
    """Raised when an order ID has already been used in this engine."""


class Side(Enum):
    """Which side of the market an order is on."""

    BUY = "BUY"
    SELL = "SELL"

    @classmethod
    def parse(cls, value: object) -> "Side":
        """Convert a Side or a string such as 'buy' / 'SELL' into a Side."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().upper())
            except ValueError:
                pass
        raise InvalidOrderError(f"Invalid order side: {value!r} (expected BUY or SELL)")

    @property
    def opposite(self) -> "Side":
        """The side an order of this side can trade against."""
        return Side.SELL if self is Side.BUY else Side.BUY


def _to_decimal(value: object) -> Decimal:
    """Convert a price into a Decimal, rejecting floats and bad values."""
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidOrderError(
            f"Price must be a Decimal, int, or str (not {type(value).__name__}); "
            "floats are rejected to avoid precision errors."
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            raise InvalidOrderError(f"Price is not a valid number: {value!r}") from None
    raise InvalidOrderError(f"Unsupported price type: {type(value).__name__}")


@dataclass
class Order:
    """A limit order.

    `sequence` and `timestamp` are assigned by the matching engine when the
    order is accepted. `remaining` starts equal to `quantity` and shrinks as
    the order is filled.
    """

    order_id: str
    symbol: str
    side: Side
    price: PriceLike
    quantity: int
    sequence: int = 0
    timestamp: float = 0.0
    remaining: int = field(init=False)

    def __post_init__(self) -> None:
        # Normalise values first, then validate.
        if not isinstance(self.order_id, str):
            raise InvalidOrderError("Order ID must be a string")
        self.order_id = self.order_id.strip()
        if isinstance(self.symbol, str):
            self.symbol = self.symbol.strip().upper()
        self.side = Side.parse(self.side)
        self.price = _to_decimal(self.price)
        self.remaining = self.quantity if isinstance(self.quantity, int) else 0
        self.validate()

    def validate(self) -> None:
        """Raise InvalidOrderError if any field is invalid.

        The engine calls this again on submission, in case a field was
        changed after the order was created.
        """
        if not isinstance(self.order_id, str) or not self.order_id:
            raise InvalidOrderError("Order ID must be a non-empty string")
        if not isinstance(self.symbol, str) or not _SYMBOL_PATTERN.fullmatch(self.symbol):
            raise InvalidOrderError(
                f"Invalid symbol: {self.symbol!r} (expected 1-10 letters A-Z)"
            )
        if not isinstance(self.side, Side):
            raise InvalidOrderError(f"Invalid order side: {self.side!r}")
        if not isinstance(self.price, Decimal) or not self.price.is_finite():
            raise InvalidOrderError(f"Price must be a finite number: {self.price!r}")
        if self.price <= 0:
            raise InvalidOrderError(f"Price must be positive, got {self.price}")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidOrderError(f"Quantity must be an integer, got {self.quantity!r}")
        if self.quantity <= 0:
            raise InvalidOrderError(f"Quantity must be positive, got {self.quantity}")
        if not 0 <= self.remaining <= self.quantity:
            raise InvalidOrderError(
                f"Remaining quantity {self.remaining} is outside 0..{self.quantity}"
            )

    @property
    def is_filled(self) -> bool:
        """True when nothing is left to trade."""
        return self.remaining == 0


@dataclass(frozen=True)
class Trade:
    """A record of one execution between a buy order and a sell order.

    Frozen (immutable) because a trade is a historical fact that must not change.
    """

    trade_id: int
    symbol: str
    price: Decimal
    quantity: int
    buy_order_id: str
    sell_order_id: str
    timestamp: float