
import multiprocessing as mp
import os

from src.ipc_producer import producer
from src.ipc_consumer import consumer

CAPACITY = 65536
FILE_PATH = "shared_orders.bin"


def main():
    mp.freeze_support()

    if os.path.exists(FILE_PATH):
        os.remove(FILE_PATH)

    # Shared producer/consumer state.
    head = mp.Value("Q", 0, lock=False)
    tail = mp.Value("Q", 0, lock=False)
    count = mp.Value("Q", 0, lock=False)

    condition = mp.Condition()
    ready = mp.Event()

    # Create the shared mmap file before starting processes.
    with open(FILE_PATH, "wb") as f:
        f.truncate(CAPACITY * 21)

    p1 = mp.Process(
        target=producer,
        args=(
            FILE_PATH, CAPACITY,
            head, tail, count, condition, ready
        )
    )

    p2 = mp.Process(
        target=consumer,
        args=(
            FILE_PATH, CAPACITY,
            head, tail, count, condition, ready
        )
    )

    p1.start()
    p2.start()

    p1.join()
    p2.join()

    if p1.exitcode != 0 or p2.exitcode != 0:
        raise RuntimeError("IPC process failed")

    os.remove(FILE_PATH)
    print("\nZero-Copy IPC test completed successfully.")


if __name__ == "__main__":
    main()
