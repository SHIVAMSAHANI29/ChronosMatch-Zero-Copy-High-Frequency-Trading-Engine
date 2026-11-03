
import mmap
import struct
import os
import multiprocessing as mp

# Binary layout
HEADER = struct.Struct("<II")   # write_index, read_index
RECORD = struct.Struct("<QdI")  # order_id, price, quantity

CAPACITY = 8
FILE_PATH = "shared_ring_buffer.bin"
HEADER_SIZE = HEADER.size
RECORD_SIZE = RECORD.size
FILE_SIZE = HEADER_SIZE + CAPACITY * RECORD_SIZE


def slot_offset(index):
    """Calculate the byte offset of a ring-buffer slot."""
    return HEADER_SIZE + index * RECORD_SIZE


def producer(empty_slots, full_slots, lock, total_orders):
    """Write binary order records into shared memory."""
    with open(FILE_PATH, "r+b") as file:
        with mmap.mmap(file.fileno(), FILE_SIZE) as mem:
            for order_id in range(1, total_orders + 1):
                order = (
                    order_id,
                    100.25 + order_id,
                    order_id * 10
                )

                # Wait until a free slot is available.
                empty_slots.acquire()

                with lock:
                    write_index, read_index = HEADER.unpack_from(mem, 0)

                    # Pack fields directly into the mapped memory.
                    RECORD.pack_into(
                        mem,
                        slot_offset(write_index),
                        *order
                    )

                    write_index = (write_index + 1) % CAPACITY
                    HEADER.pack_into(
                        mem, 0, write_index, read_index
                    )

                # Notify the consumer that a record is ready.
                full_slots.release()

            # Send a termination record (order ID 0 is reserved).
            empty_slots.acquire()
            with lock:
                write_index, read_index = HEADER.unpack_from(mem, 0)
                RECORD.pack_into(
                    mem, slot_offset(write_index), 0, 0.0, 0
                )
                write_index = (write_index + 1) % CAPACITY
                HEADER.pack_into(mem, 0, write_index, read_index)

            full_slots.release()


def consumer(empty_slots, full_slots, lock):
    """Read binary order records from shared memory."""
    with open(FILE_PATH, "r+b") as file:
        with mmap.mmap(file.fileno(), FILE_SIZE) as mem:
            while True:
                # Wait until a record is available.
                full_slots.acquire()

                with lock:
                    write_index, read_index = HEADER.unpack_from(mem, 0)

                    order = RECORD.unpack_from(
                        mem, slot_offset(read_index)
                    )

                    read_index = (read_index + 1) % CAPACITY
                    HEADER.pack_into(
                        mem, 0, write_index, read_index
                    )

                # The slot is now free for reuse.
                empty_slots.release()

                order_id, price, quantity = order

                if order_id == 0:
                    break

                print(
                    f"Order ID: {order_id}, "
                    f"Price: {price:.2f}, "
                    f"Quantity: {quantity}"
                )


def main():
    total_orders = 20

    # Create and initialize the shared memory-mapped file.
    with open(FILE_PATH, "w+b") as file:
        file.truncate(FILE_SIZE)

    with open(FILE_PATH, "r+b") as file:
        with mmap.mmap(file.fileno(), FILE_SIZE) as mem:
            mem[:] = b"\x00" * FILE_SIZE
            HEADER.pack_into(mem, 0, 0, 0)

    # Process-safe synchronization primitives.
    empty_slots = mp.Semaphore(CAPACITY)
    full_slots = mp.Semaphore(0)
    lock = mp.Lock()

    p_consumer = mp.Process(
        target=consumer,
        args=(empty_slots, full_slots, lock)
    )
    p_producer = mp.Process(
        target=producer,
        args=(empty_slots, full_slots, lock, total_orders)
    )

    try:
        p_consumer.start()
        p_producer.start()

        p_producer.join()
        p_consumer.join()

        if p_producer.exitcode != 0 or p_consumer.exitcode != 0:
            raise RuntimeError("A process failed")

    finally:
        for process in (p_producer, p_consumer):
            if process.is_alive():
                process.terminate()
                process.join()

        if os.path.exists(FILE_PATH):
            os.remove(FILE_PATH)


if __name__ == "__main__":
    mp.freeze_support()
    main()
