
import mmap
import os
import struct

# Binary order record:
# Order ID: unsigned 64-bit integer
# Price: double
# Quantity: unsigned 32-bit integer
# Side: unsigned 8-bit integer (0=BUY, 1=SELL)

RECORD = struct.Struct("<QdIB")

RECORD_SIZE = RECORD.size

BUY = 0
SELL = 1


class SharedRingBuffer:
    def __init__(self, path, capacity, create=False):
        self.path = path
        self.capacity = capacity
        self.size = capacity * RECORD_SIZE

        if create:
            with open(path, "wb") as f:
                f.truncate(self.size)

        self.file = open(path, "r+b")
        self.mm = mmap.mmap(self.file.fileno(), self.size)

    def write(self, index, order_id, price, quantity, side):
        offset = (index % self.capacity) * RECORD_SIZE

        # Write directly into mapped memory.
        RECORD.pack_into(
            self.mm,
            offset,
            order_id,
            price,
            quantity,
            side
        )

    def read(self, index):
        offset = (index % self.capacity) * RECORD_SIZE

        # Read directly from mapped memory.
        return RECORD.unpack_from(self.mm, offset)

    def close(self):
        self.mm.close()
        self.file.close()
