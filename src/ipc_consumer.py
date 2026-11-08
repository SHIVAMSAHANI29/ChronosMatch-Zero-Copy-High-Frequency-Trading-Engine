
import time
from src.zero_copy_ipc import SharedRingBuffer

TOTAL_ORDERS = 1_000_000
BATCH_SIZE = 1024


def consumer(path, capacity, head, tail, count, condition, ready):
    buffer = SharedRingBuffer(path, capacity)

    received = 0
    checksum = 0

    start = time.perf_counter_ns()

    try:
        while received < TOTAL_ORDERS:

            with condition:
                while count.value == 0:
                    condition.wait()

                available = min(BATCH_SIZE, count.value)

                for _ in range(available):
                    order_id, price, quantity, side = buffer.read(
                        tail.value
                    )

                    # Replace this section with your matching engine.
                    checksum += order_id

                    tail.value = (tail.value + 1) % capacity
                    count.value -= 1
                    received += 1

                condition.notify_all()

        elapsed = time.perf_counter_ns() - start

        print(f"Consumer received: {received:,} orders")
        print(f"Checksum: {checksum}")
        print(f"Consumer time: {elapsed / 1e9:.3f} seconds")
        print(f"Throughput: {received / (elapsed / 1e9):,.0f} orders/sec")

    finally:
        buffer.close()
