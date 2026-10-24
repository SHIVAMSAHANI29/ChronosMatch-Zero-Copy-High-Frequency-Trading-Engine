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

# ChronosMatch — Week 2
## Cython Matching Engine & Real-Time Latency Dashboard

**Project:** ChronosMatch: Zero-Copy High-Frequency Trading Engine  
**Domain:** FinTech, Low-Latency Systems & Systems Programming  
**Phase:** Week 2 — Matching Engine Integration  
**Language:** Python, Cython, C  
**Core Technologies:** `Cython`, `mmap`, `struct`, `asyncio`, `curses`, `time.perf_counter_ns()`

---

## 1. Overview

ChronosMatch is a low-latency trading engine designed to demonstrate how memory-mapped inter-process communication (IPC), Cython-based order matching, and efficient data structures can be combined to build a high-performance financial matching system.

Week 2 extends the Week 1 memory-mapped ring buffer by introducing a Cython-based Limit Order Book (LOB), implementing price-time priority, and developing a real-time terminal dashboard for monitoring market activity.

The objective is to reduce Python overhead in the critical matching path while maintaining correctness, observability, and compatibility with the existing zero-copy IPC architecture.

## 2. Week 2 Objectives

- Implement the Limit Order Book algorithm using Cython.
- Apply price-time priority to incoming buy and sell orders.
- Use statically typed Cython variables in performance-critical sections.
- Integrate the matching engine with the existing `mmap` IPC ring buffer.
- Develop a real-time terminal dashboard using `curses`.
- Display best bid, best ask, bid-ask spread, and matching activity.
- Verify order matching, partial fills, and price-time ordering.
- Establish a foundation for latency measurement and optimization in Week 3.

## 3. System Architecture

```text
       Market Order Generator
                |
                v
        Asyncio Order Producer
                |
                v
      Memory-Mapped Ring Buffer
          (mmap + struct)
                |
                v
        Cython Order Consumer
                |
                v
        Limit Order Book
       (Price-Time Priority)
                |
         +------+------+
         |             |
         v             v
   Matched Trades   Open Orders
         |             |
         +------+------+
                |
                v
       Real-Time Dashboard
             (curses)
```

The ring buffer provides shared-memory communication between processes. The consumer reads encoded order records and passes them to the matching engine, which maintains the order book and generates trade executions.

The dashboard presents a live view of market state and engine activity.

## 4. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application orchestration and IPC integration |
| Cython | Compiling performance-critical matching logic |
| C types | Reducing Python object overhead in suitable code paths |
| `mmap` | Sharing data through memory-mapped regions |
| `struct` | Encoding and decoding fixed-size binary order records |
| `asyncio` | Asynchronous order generation and coordination |
| `curses` | Real-time terminal-based market visualization |
| `time.perf_counter_ns()` | High-resolution elapsed-time measurement |
| SQLite (planned) | Persistent trade ledger in Week 4 |

## 5. Limit Order Book Implementation

The Week 2 matching engine follows these rules:

### Order types

- **BUY:** An order to purchase an asset at a specified limit price.
- **SELL:** An order to sell an asset at a specified limit price.

### Matching conditions

A buy order matches the best available sell order when:

`buy_price >= best_ask_price`

A sell order matches the best available buy order when:

`sell_price <= best_bid_price`

### Price-time priority

1. Buy orders are prioritized by highest price.
2. Sell orders are prioritized by lowest price.
3. Orders at the same price are prioritized by arrival time.
4. A trade executes at the resting order's price.
5. Partially filled orders remain in the book with their remaining quantity.
6. Fully filled orders are removed from the active book.
7. Each order has a unique identifier.

### Example

Suppose the order book contains:

| Side | Order ID | Price | Quantity |
|---|---|---:|---:|
| SELL | S101 | ₹100.00 | 10 |
| SELL | S102 | ₹101.00 | 20 |

A new BUY order arrives:

| Order ID | Price | Quantity |
|---|---:|---:|
| B201 | ₹101.00 | 15 |

Expected execution:

- 10 units match against S101 at ₹100.00.
- The remaining 5 units match against S102 at ₹101.00.
- Both sell orders are processed according to price priority.
- S102 retains 15 units after the partial fill.
- B201 is fully filled.

This demonstrates multi-level matching and correct execution-price behavior.

## 6. Cython Engine Design

The matching algorithm is implemented in `.pyx` files and compiled into a native extension.

The performance-critical path should use appropriate Cython declarations, such as:

```cython
cdef int quantity
cdef long long price
cdef long long order_id
```

The exact types must match the binary order format and supported numeric ranges.

Optimization goals include:

- Minimizing Python object creation in matching loops.
- Reducing repeated attribute lookups and dynamic dispatch.
- Using efficient order-book data structures.
- Keeping order parsing and matching operations predictable.
- Separating dashboard rendering from the matching thread or process.

**Important:** Cython does not automatically eliminate the GIL. Python object operations generally require it. The `nogil` feature is appropriate only when the code inside the relevant section is safe to execute without Python interaction. A fully GIL-free matching loop requires suitable native data structures and operations.

## 7. Memory-Mapped IPC Integration

Week 2 reuses the Week 1 shared-memory transport.

Each order is encoded as a fixed-size binary record containing fields such as:

- Order ID
- Price
- Quantity
- Side
- Sequence number or timestamp, if included in the record format

The producer writes records to the ring buffer, and the consumer reads them without serializing Python objects through Pickle.

The implementation must maintain:

- A consistent binary record layout.
- Correct read and write positions.
- Ring-buffer wraparound handling.
- Synchronization between producers and consumers.
- Full-buffer and empty-buffer handling.
- Validation of incoming order records.

A memory-mapped file alone does not guarantee a correct lock-free ring buffer. Shared indices, publication ordering, and synchronization must be implemented and tested explicitly.

## 8. Real-Time Latency Dashboard

The Week 2 dashboard uses Python's `curses` module to display a continuously updated terminal interface.

### Dashboard fields

- Best bid price and quantity
- Best ask price and quantity
- Bid-ask spread
- Number of orders processed
- Number of matched trades
- Open buy and sell orders
- Recent trade executions
- Engine status and processing errors

### Example terminal layout

```text
+------------------------------------------------------+
|             CHRONOSMATCH TRADING ENGINE              |
+------------------------------------------------------+
| ENGINE STATUS: RUNNING                               |
| ORDERS PROCESSED: 125,430                             |
| MATCHED TRADES: 48,291                                |
+------------------------------------------------------+
| BEST BID                 BEST ASK                     |
| Price:  100.50           Price:  100.75               |
| Qty:    250              Qty:    180                  |
|                                                      |
| BID-ASK SPREAD: 0.25                                  |
+------------------------------------------------------+
| RECENT TRADES                                         |
| BUY/SELL      PRICE          QUANTITY                 |
| B201/S101     100.50         10                       |
| B202/S103     100.25         20                       |
+------------------------------------------------------+
| PRESS Q TO QUIT                                       |
+------------------------------------------------------+
```

The values above are illustrative, not measured benchmark results.

The dashboard should refresh at a controlled interval so that terminal rendering does not become a bottleneck for order processing.

## 9. Suggested Project Structure

Adapt the following structure to the actual Week 1 repository rather than duplicating existing modules.

```text
ChronosMatch/
├── src/
│   ├── api.py
│   ├── config.py
│   ├── main.py
│   ├── matching_engine.py
│   ├── models.py
│   ├── order_book.py
│   └── persistence.py
├── ipc/
│   ├── ipc_ring.py
│   └── ipc_audit.py
├── engine/
│   ├── engine.pyx
│   ├── engine.pxd
│   └── setup.py
├── dashboard/
│   └── dashboard.py
├── tests/
│   ├── test_matching.py
│   ├── test_price_time_priority.py
│   ├── test_partial_fills.py
│   └── test_ipc_integration.py
├── requirements.txt
└── README.md
```

The directory layout is a suggested organization. Preserve your existing import paths and module names when integrating these files into the Week 1 project.

## 10. Installation and Setup

### Prerequisites

- Python 3.10 or later, subject to dependency compatibility
- A C compiler supported by the installed Cython toolchain
- Cython
- A terminal supporting `curses`

On Windows, the standard Unix `curses` module is not normally available. Use an appropriate Windows-compatible implementation or run the dashboard through WSL/Linux.

### Create a virtual environment

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

### Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install cython
```

Install any additional packages listed in the repository's `requirements.txt`.

### Compile the Cython extension

From the directory containing the relevant `setup.py`:

```bash
python setup.py build_ext --inplace
```

The build command and extension name must match the actual setup configuration.

## 11. Running the Project

The exact commands depend on the existing Week 1 entry points.

A typical development workflow is:

1. Compile the Cython matching engine.
2. Start the memory-mapped IPC consumer.
3. Launch the order-book matching process.
4. Start the asynchronous market-order producer.
5. Launch the terminal dashboard.
6. Observe order processing, matches, and book updates.

For example, if these entry points exist:

```bash
python -m src.main
```

```bash
python dashboard/dashboard.py
```

These commands are examples only; adjust them to the actual files and process-launching logic in your repository.

## 12. Week 2 Verification Plan

### Test 1: Basic matching

Submit a SELL order at ₹100 and a BUY order at ₹100 or higher.

Expected result: The engine executes the compatible quantity at the resting order's price.

### Test 2: Non-matching orders

Submit a BUY order at ₹99 and a SELL order at ₹100.

Expected result: Both orders remain in the book without an execution.

### Test 3: Price priority

Insert multiple sell orders at different prices.

Expected result: The lowest-priced eligible sell order is matched first.

### Test 4: Time priority

Insert two orders at the same price, with different arrival sequence numbers.

Expected result: The earlier order is matched first.

### Test 5: Partial fills

Submit an order whose quantity exceeds that of the best resting order.

Expected result: The engine executes the available quantity and continues matching until the incoming order is filled or no eligible orders remain.

### Test 6: IPC integration

Send a sequence of encoded orders through the memory-mapped ring buffer.

Expected result: The consumer decodes the records correctly, and the resulting order-book state matches the expected state.

### Test 7: Dashboard integration

Run the engine with a stream of mock orders.

Expected result: The displayed best bid, best ask, spread, and trade counters reflect the engine's current state.

## 13. Mid-Project Review

The mid-project review evaluates the integration of the memory-mapped IPC layer and the matching engine.

### IPC audit

- Transfer 1,000,000 test orders between two Python processes.
- Validate record integrity and sequence ordering.
- Measure throughput and CPU utilization.
- Compare the shared-memory implementation with an appropriate Pickle-based baseline.
- Record dropped, duplicated, or corrupted records, if any.

The goal is to demonstrate reduced serialization and copying overhead. The test must measure actual behavior; zero-copy claims should be limited to the specific data path that avoids payload copying.

### Engine verification

- Verify compatible buy and sell orders match.
- Verify non-crossing orders remain open.
- Verify price-time priority.
- Verify partial fills and resting-price execution.
- Confirm that the resulting order book is internally consistent.

## 14. Performance Measurement

Week 2 establishes the foundation for formal latency testing in Week 3.

Record timestamps using `time.perf_counter_ns()` at appropriate boundaries:

```python
import time

start_ns = time.perf_counter_ns()

# Submit or process an order.

end_ns = time.perf_counter_ns()
elapsed_ns = end_ns - start_ns

print(f"Elapsed time: {elapsed_ns} ns")
```

This example measures the elapsed time around the code block. To measure engine-only latency, place the timestamps immediately around the matching operation.

Report median, p95, p99, and maximum latency alongside throughput and test conditions. Keep producer-to-consumer transport latency separate from matching-engine execution latency.

Do not report a sub-millisecond execution target as an achieved result until it has been measured under documented test conditions.

## 15. Week 2 Deliverables

- Cython-based Limit Order Book implementation.
- Price-time priority matching logic.
- Integration with the Week 1 memory-mapped ring buffer.
- Real-time `curses` dashboard.
- Unit tests for matching, order priority, and partial fills.
- IPC integration tests and audit results.
- Initial performance measurements.
- Updated technical documentation.

## 16. Known Limitations and Next Steps

Week 2 focuses on functional integration and initial optimization. Further work is required before treating the engine as a production-grade trading system.

Potential limitations include:

- Synchronization overhead in the shared-memory ring buffer.
- Python object creation outside the native matching loop.
- Dashboard refresh overhead.
- Missing recovery mechanisms for process failures.
- Lack of durable trade persistence.
- Need for more comprehensive concurrency and stress testing.

### Week 3 — C-Level Optimization

- Reduce Python object interactions inside the matching loop.
- Optimize Cython data structures and hot paths.
- Introduce consistent nanosecond timing instrumentation.
- Measure throughput, median latency, p95, and p99 latency.

### Week 4 — Resiliency and Persistence

- Flush matched trades asynchronously to SQLite or ClickHouse.
- Add auditing and recovery mechanisms.
- Highlight large orders that consume multiple price levels.
- Refine the terminal dashboard.
- Perform end-to-end performance and reliability tests.

## 17. Project Outcome

ChronosMatch Week 2 demonstrates the integration of a compiled Cython matching engine, price-time priority, memory-mapped IPC, and a real-time terminal dashboard within the Python ecosystem.

The project provides a foundation for exploring low-latency systems engineering, shared-memory communication, native-code optimization, and financial order-matching logic.

**Project objective:** Build and verify a low-latency matching engine, then quantify its performance through reproducible benchmarks rather than relying on theoretical targets.

---

*ChronosMatch — Engineering the path from Python orchestration to native-speed market logic.*

