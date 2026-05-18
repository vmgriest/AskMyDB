import struct
from typing import List, Optional

PAGE_SIZE = 4096
_MAGIC = b"AMDB"
# Header layout: magic(4) + num_records(4) + next_page_id(4) = 12 bytes
_HEADER = 12


class Page:
    """
    Heap page with a simple append-only record layout.

    Header (12 bytes):
        [0:4]  magic "AMDB"
        [4:8]  num_records  (uint32, big-endian)
        [8:12] next_page_id (int32, big-endian; -1 = no next page)

    Body: records packed consecutively after the header.
        Each record: [length: uint32][data: bytes]
    """

    def __init__(self, page_id: int, data: bytes = None):
        self.page_id = page_id
        self.dirty = False
        if data:
            self._buf = bytearray(data)
        else:
            self._buf = bytearray(PAGE_SIZE)
            self._buf[0:4] = _MAGIC
            struct.pack_into(">I", self._buf, 4, 0)   # num_records = 0
            struct.pack_into(">i", self._buf, 8, -1)  # next_page_id = -1

    # ── properties ───────────────────────────────────────────────────────────

    @property
    def num_records(self) -> int:
        return struct.unpack_from(">I", self._buf, 4)[0]

    @property
    def next_page_id(self) -> int:
        return struct.unpack_from(">i", self._buf, 8)[0]

    @next_page_id.setter
    def next_page_id(self, val: int):
        struct.pack_into(">i", self._buf, 8, val)
        self.dirty = True

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _free_offset(self) -> int:
        """Byte offset of the first free slot after all existing records."""
        offset = _HEADER
        for _ in range(self.num_records):
            length = struct.unpack_from(">I", self._buf, offset)[0]
            offset += 4 + length
        return offset

    def insert_record(self, record: bytes) -> Optional[int]:
        """Append a record. Returns slot index on success, None if page is full."""
        offset = self._free_offset()
        needed = 4 + len(record)
        if offset + needed > PAGE_SIZE:
            return None
        struct.pack_into(">I", self._buf, offset, len(record))
        self._buf[offset + 4 : offset + 4 + len(record)] = record
        slot = self.num_records
        struct.pack_into(">I", self._buf, 4, slot + 1)
        self.dirty = True
        return slot

    def get_records(self) -> List[bytes]:
        records = []
        offset = _HEADER
        for _ in range(self.num_records):
            length = struct.unpack_from(">I", self._buf, offset)[0]
            records.append(bytes(self._buf[offset + 4 : offset + 4 + length]))
            offset += 4 + length
        return records

    def to_bytes(self) -> bytes:
        return bytes(self._buf)
