# System Design: ChronosMatch Week 1

## 1. Architecture overview

```text
 main.py / benchmark.py / tests
              │
              ▼
   src/matching_engine.py    WHEN and HOW trades happen
              │
              ▼
      src/order_book.py      WHERE orders are stored, in WHAT order
              │
              ▼
        src/models.py        WHAT an order and a trade are
```

Dependencies point one way (downward). Each layer can be changed or tested
without touching the one above it.

## 2. Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `models.py` | `Side` enum, `Order` dataclass with validation, immutable `Trade` dataclass, error types. |
| `order_book.py` | `OrderBook`: two heaps (BUY, SELL) for one symbol; `add`, `best`, `pop_best`, `orders`. No trading logic. |
| `matching_engine.py` | `MatchingEngine`: one book per symbol, sequence numbers, duplicate detection, matching loop, trade history. |
| `main.py` | Demo only; no business logic. |
| `benchmark.py` | Generates simulated orders and times order creation and matching. |

## 3. Order lifecycle

1. **Created:** `Order(...)` normalises and validates fields; `remaining = quantity`.
2. **Submitted:** `engine.submit_order(order)` re-validates, checks for a duplicate ID and a partly-filled state. Any failure raises an error and changes nothing.
3. **Accepted:** the ID is recorded and the order receives its sequence number and timestamp.
4. **Matched:** the engine trades it against the best opposing orders while prices cross.
5. **Resting or done:** if `remaining > 0` the order is added to the book; if `remaining == 0` it is finished and never enters the book.
6. **Later:** a resting order may be filled by future incoming orders and is then removed from the book.

## 4. Matching algorithm

```text
submit_order(order):
    validate; reject duplicates         (no state change on failure)
    assign sequence number and timestamp
    book = book for order.symbol (create if needed)
    while order.remaining > 0:
        resting = best order on the opposite side
        if none, or prices do not cross: stop
        qty = min(order.remaining, resting.remaining)
        record Trade(price = resting.price, quantity = qty)
        subtract qty from both orders
        if resting.remaining == 0: remove it from the book
    if order.remaining > 0: add order to the book
```

**Cross condition:** incoming BUY crosses if `buy_price >= resting_sell_price`;
incoming SELL crosses if `sell_price <= resting_buy_price`.

**Execution price rule:** the **resting order's price**. Example: a resting BUY
@100 meets an incoming SELL @99, so the trade is at 100. This rule is simple and
deterministic. It is a design choice, not an official requirement, and other
rules exist (for example, the incoming order's price).

**Termination:** each loop iteration fully exhausts at least one order, so the
loop ends.

## 5. Price-time priority

Each heap entry is `(price_key, sequence, order)`.

- BUY: `price_key = -price`, so the highest price is the smallest key.
- SELL: `price_key = +price`, so the lowest price is the smallest key.
- Ties on price are broken by the smaller sequence number (earlier arrival).

Sequence numbers are unique, so tuple comparison never reaches the `Order`
object. Time uses a sequence counter, not the clock, because timestamps can
tie or go backwards; timestamps are stored for display only.

## 6. Data structures

| Structure | Where | Why |
|-----------|-------|-----|
| `heapq` list (min-heap) ×2 per symbol | `OrderBook` | Best order is always at index 0; push/pop are O(log n). |
| `dict[str, OrderBook]` | engine | One book per symbol; isolation by construction. |
| `set[str]` of order IDs | engine | O(1) average duplicate check. |
| `list[Trade]` | engine | Ordered trade history. |
| `itertools.count` | engine | Strictly increasing sequence and trade IDs. |
| frozen `dataclass` | `Trade` | Immutable historical record. |

## 7. Complexity analysis

Let `n` be the number of open orders in one book and `k` the number of resting orders consumed by one submission.

| Operation | Time |
|-----------|------|
| Peek best order (`best`) | O(1) |
| Add an order to the book | O(log n) |
| Remove the best order (`pop_best`) | O(log n) |
| `submit_order` | O(k log n) for matching plus O(log n) to rest the remainder, plus O(1) average for the ID check |
| `orders()` (display) | O(n log n); builds a sorted copy |
| `total_traded_quantity` / `total_traded_value` | O(T) over T trades (recomputed on each call) |

Space is O(n) for open orders, plus O(T) for trades and O(N) for remembered
order IDs (N = all orders ever accepted).

## 8. Zero-copy and performance awareness

**What zero-copy means.** Normally, moving data between components can create
duplicate copies of it, for example copying a buffer from one place to another
or building a new list or object at each stage. A zero-copy design passes
*references or views* to the same memory instead, so the bytes are not
duplicated.

**Why copying matters.** Each copy costs CPU time, uses memory, and creates
work for the memory allocator and garbage collector. In a system that handles
very large numbers of messages per second, this overhead can add latency and
make timings less predictable.

**Normal Python vs. genuinely optimized design.** This baseline is a normal
Python design. Examples of where it copies or allocates:
- `orders()` builds a new sorted list each time it is called.
- The `trades` property returns a new list copy.
- Every order and trade is a Python object with its own allocation.

A genuinely optimized zero-copy design would typically use preallocated
buffers or arrays, views into shared memory (such as `memoryview`), and
compact fixed-layout records instead of many small objects. Python has
limits here, and truly low-latency engines are usually written in languages
like C++ or Rust. I have not built or measured any such design.

**Why correctness comes first.** An optimization can only be judged against a
version known to be correct. The Week 1 tests and baseline timings give a
reference to compare Week 2+ changes against, and they catch optimizations that
quietly break priority or partial-fill behavior.

**Measuring with `time.perf_counter()`.** It is a high-resolution clock for
measuring elapsed time:

```python
start = time.perf_counter()
# ... code being measured ...
elapsed = time.perf_counter() - start
```

`benchmark.py` times two things separately: (1) order creation, which includes
random data generation and validation, and (2) `submit_order` for all orders,
which includes re-validation, duplicate check, matching, and resting.
It reports measurements only when you run it; no results are assumed here.

## 9. Limitations and possible optimizations

**Limitations**
- Limit orders only; no cancel or modify
- The engine mutates caller-owned `Order` objects
- Order IDs are never forgotten, so memory grows
- `orders()` and `trades` copy data
- Single-threaded, in-memory, not production-grade

**Possible optimizations (Week 2+, to be measured before and after)**
- Group orders into price levels, each with a queue, so best-price access and cancellation are cheaper
- Use `__slots__` or compact records to reduce per-object overhead
- Avoid copies on read paths (iterate or expose views instead of building lists)
- Cache running totals instead of recomputing them
- Profile first, then optimize the measured bottlenecks