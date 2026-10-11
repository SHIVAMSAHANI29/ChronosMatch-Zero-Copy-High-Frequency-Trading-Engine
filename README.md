# ChronosMatch: Zero-Copy High-Frequency Trading Engine (Week 1 Baseline)

An educational limit-order matching engine written in Python as part of a
one-month Python Development internship project.

> **Honest scope note:** Week 1 builds a *correct, tested baseline*. It is **not**
> zero-copy and **not** production-grade high-frequency trading software.
> Zero-copy optimization is a later-week goal. All prices in the examples are
> artificial and are not real market data.

## Overview

ChronosMatch simulates the core of a stock exchange: it accepts BUY and SELL
limit orders, matches them using price-time priority, supports partial fills,
and records every executed trade.

## Features

- BUY and SELL limit orders with validated fields
- `Decimal` prices (no floating-point rounding errors)
- Separate order book per stock symbol (symbols never match each other)
- Price-time priority: best price first, then earliest arrival
- Partial fills; unfilled remainder rests in the book
- Trade execution at the **resting order's price**
- Rejection of invalid orders and duplicate order IDs
- Command-line demo, optional benchmark, and `unittest` test suite
- Standard library only: no external dependencies

## Requirements

- Python 3.11 or newer
- Windows, macOS, or Linux (commands below are for Windows PowerShell)
- VS Code with the Microsoft Python extension (recommended)

## Installation

```powershell
cd ChronosMatch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

No `pip install` is needed. `requirements.txt` has no packages in Week 1.

## Running the application

```powershell
python main.py
```

Optional benchmark (prints measurements; your numbers depend on your machine):

```powershell
python benchmark.py --orders 20000
```

## Running the tests

```powershell
python -m unittest -v
```

A successful run ends with `Ran N tests in ...s` followed by `OK`.

## Example output

*Hand-traced expectation. Replace with your actual output after running.*

```text
--- Submitting orders ---
SUBMIT B1: BUY 10 AAPL @ ₹100.00
  -> 10 of 10 resting in the book
SUBMIT S1: SELL 4 AAPL @ ₹100.00
  -> TRADE #1: AAPL 4 @ ₹100.00 (buy B1, sell S1)
SUBMIT S2: SELL 6 AAPL @ ₹99.00
  -> TRADE #2: AAPL 6 @ ₹100.00 (buy B1, sell S2)
SUBMIT B2: BUY 5 MSFT @ ₹200.00
  -> 5 of 5 resting in the book
SUBMIT S3: SELL 5 MSFT @ ₹205.00
  -> 5 of 5 resting in the book
...
Total trades: 2
Total traded quantity: 10
Total traded value: ₹1,000.00
```

## Project structure

```text
ChronosMatch/
├── main.py                 CLI demo
├── benchmark.py            optional benchmark
├── src/
│   ├── models.py           Side, Order, Trade, error types
│   ├── order_book.py       per-symbol priority storage
│   └── matching_engine.py  validation, matching, trade records
├── tests/                  unittest suite
└── docs/                   requirements, design, progress report
```

## Key design decisions

- **Execution price = resting order's price** (the order already in the book).
- **Time priority uses a sequence counter**, not the wall clock, so ordering is
  unambiguous and tests are deterministic.
- **One order book per symbol**, so cross-symbol matching is impossible by design.

See `docs/system_design.md` for details, including what "zero-copy" means and
why this baseline is not it.

## Current limitations

- Limit orders only (no market orders)
- No order cancellation or modification
- No persistence: everything is lost when the program exits
- Single-threaded; no network interface
- The engine mutates the `Order` objects passed to it
- Used order IDs are remembered forever, so memory grows with order count
- Symbols are limited to 1-10 letters A-Z (an assumption)
- Prices given as Python `float` are rejected on purpose; use `int`, `str`, or `Decimal`
- Not zero-copy, not optimized, and not suitable for real trading

## Future improvements (Weeks 2-4, planned and not yet done)

- Order cancellation and market orders
- Reduce copying and allocation in the hot path; measure with the benchmark
- Faster data structures (e.g. price-level queues)
- Richer benchmarks and profiling
- Persistence or logging of trades