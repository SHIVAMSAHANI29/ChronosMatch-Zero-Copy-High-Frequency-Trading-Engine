
import time
from src.zero_copy_ipc import SharedRingBuffer, BUY, SELL

TOTAL_ORDERS = 1_000_000
BATCH_SIZE = 1024


def producer(path, capacity, head, tail, count, condition, ready):
    buffer = SharedRingBuffer(path, capacity)

    produced = 0
    start = time.perf_counter_ns()

    try:
        while produced < TOTAL_ORDERS:

            with condition:
                while count.value == capacity:
                    condition.wait()

                available = min(
                    BATCH_SIZE,
                    capacity - count.value,
                    TOTAL_ORDERS - produced
                )

                for _ in range(available):
                    order_id = produced + 1
                    price = 65000.0 + (produced % 100)
                    quantity = 10
                    side = BUY if produced % 2 == 0 else SELL

                    buffer.write(
                        head.value,
                        order_id,
                        price,
                        quantity,
                        side
                    )

                    head.value = (head.value + 1) % capacity
                    count.value += 1
                    produced += 1

                condition.notify_all()

        elapsed = time.perf_counter_ns() - start

        print(f"Producer completed: {produced:,} orders")
        print(f"Producer time: {elapsed / 1e9:.3f} seconds")

    finally:
        ready.set()
        buffer.close()
