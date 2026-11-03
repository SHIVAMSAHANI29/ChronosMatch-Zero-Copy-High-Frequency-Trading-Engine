
"""
ChronosMatch - 1 Million Order Zero-Copy-Style IPC Audit

One producer and one consumer process communicate through a shared
memory-mapped file. Order payloads are binary records, not Pickled objects.
"""

import argparse
import mmap
import os
import struct
import tempfile
import time
import multiprocessing as mp

# Shared memory layout:
# write_count, read_count, received_count, errors
HEADER = struct.Struct("<QQQQ")

# Each order: order_id, price, quantity
ORDER = struct.Struct("<QdI")

TOTAL_ORDERS = 1_000_000
CAPACITY = 4096


def expected_order(sequence):
    order_id = sequence + 1
    price = 100.0 + (sequence % 10000) / 100.0
    quantity = (sequence % 100) + 1
    return order_id, price, quantity


def producer(path, total, capacity, condition, done):
    """Write binary orders into the shared mmap ring buffer."""

    try:
        with open(path, "r+b") as file:
            with mmap.mmap(file.fileno(), 0) as shared:

                for sequence in range(total):
                    with condition:
                        write_count, read_count, received, errors = (
                            HEADER.unpack_from(shared, 0)
                        )

                        while write_count - read_count >= capacity:
                            condition.wait()
                            write_count, read_count, received, errors = (
                                HEADER.unpack_from(shared, 0)
                            )

                        order_id, price, quantity = expected_order(sequence)

                        slot = write_count % capacity
                        offset = HEADER.size + slot * ORDER.size

                        ORDER.pack_into(
                            shared,
                            offset,
                            order_id,
                            price,
                            quantity
                        )

                        HEADER.pack_into(
                            shared,
                            0,
                            write_count + 1,
                            read_count,
                            received,
                            errors
                        )

                        condition.notify_all()

    finally:
        with condition:
            done.set()
            condition.notify_all()


def consumer(path, total, capacity, condition, done):
    """Read and verify orders directly from the shared mmap buffer."""

    with open(path, "r+b") as file:
        with mmap.mmap(file.fileno(), 0) as shared:

            expected_sequence = 0

            while expected_sequence < total:

                with condition:
                    write_count, read_count, received, errors = (
                        HEADER.unpack_from(shared, 0)
                    )

                    while read_count >= write_count:
                        if done.is_set():
                            break
                        condition.wait()
                        write_count, read_count, received, errors = (
                            HEADER.unpack_from(shared, 0)
                        )

                    if read_count >= write_count:
                        if done.is_set():
                            break
                        continue

                    slot = read_count % capacity
                    offset = HEADER.size + slot * ORDER.size

                    order_id, price, quantity = ORDER.unpack_from(
                        shared, offset
                    )

                    expected = expected_order(expected_sequence)

                    if (
                        order_id != expected[0]
                        or price != expected[1]
                        or quantity != expected[2]
                    ):
                        errors += 1

                    HEADER.pack_into(
                        shared,
                        0,
                        write_count,
                        read_count + 1,
                        received + 1,
                        errors
                    )

                    expected_sequence += 1
                    condition.notify_all()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--orders",
        type=int,
        default=TOTAL_ORDERS
    )
    args = parser.parse_args()

    total = args.orders
    capacity = CAPACITY

    if total <= 0:
        raise ValueError("Number of orders must be positive")

    file_size = HEADER.size + capacity * ORDER.size

    # Create a shared file-backed memory region.
    fd, path = tempfile.mkstemp(prefix="chronosmatch_ipc_")
    os.close(fd)

    try:
        with open(path, "wb") as file:
            file.truncate(file_size)

        ctx = mp.get_context("spawn")
        condition = ctx.Condition(ctx.Lock())
        done = ctx.Event()

        print("=" * 55)
        print("CHRONOSMATCH - IPC AUDIT")
        print("=" * 55)
        print("Transport: Shared memory-mapped ring buffer")
        print("Order serialization: Binary struct records")
        print("Pickle used for order payload: NO")
        print(f"Orders to transfer: {total:,}")
        print()

        consumer_process = ctx.Process(
            target=consumer,
            args=(path, total, capacity, condition, done),
            name="IPC-Consumer"
        )

        producer_process = ctx.Process(
            target=producer,
            args=(path, total, capacity, condition, done),
            name="IPC-Producer"
        )

        start = time.perf_counter()

        consumer_process.start()
        producer_process.start()

        producer_process.join()
        consumer_process.join()

        elapsed = time.perf_counter() - start

        if producer_process.exitcode != 0:
            raise RuntimeError(
                f"Producer failed: {producer_process.exitcode}"
            )

        if consumer_process.exitcode != 0:
            raise RuntimeError(
                f"Consumer failed: {consumer_process.exitcode}"
            )

        with open(path, "r+b") as file:
            with mmap.mmap(file.fileno(), 0) as shared:
                written, read, received, errors = HEADER.unpack_from(
                    shared, 0
                )

        throughput = received / elapsed if elapsed else 0

        print("--------------- RESULTS ----------------")
        print(f"Orders written:       {written:,}")
        print(f"Orders read:          {read:,}")
        print(f"Orders verified:      {received:,}")
        print(f"Data errors:          {errors:,}")
        print(f"Elapsed time:         {elapsed:.3f} seconds")
        print(f"Throughput:           {throughput:,.0f} orders/second")

        passed = (
            written == total
            and read == total
            and received == total
            and errors == 0
        )

        if passed:
            print("\nIPC AUDIT: PASSED")
            print("All orders transferred and verified.")
        else:
            print("\nIPC AUDIT: FAILED")
            raise RuntimeError("IPC verification failed")

    finally:
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    mp.freeze_support()
    main()
