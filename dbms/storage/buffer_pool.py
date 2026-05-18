from collections import OrderedDict
from typing import Optional, Tuple

from .disk_manager import DiskManager
from .page import Page


class BufferPool:
    """
    LRU cache of pages sitting in front of the disk manager.

    Pages are keyed by (table_name, page_id).  When the cache is full the
    least-recently-used dirty page is written to disk and evicted.
    """

    def __init__(self, disk: DiskManager, capacity: int = 64):
        self.disk = disk
        self.capacity = capacity
        self._cache: OrderedDict[Tuple[str, int], Page] = OrderedDict()

    # ── public interface ──────────────────────────────────────────────────────

    def fetch_page(self, table: str, page_id: int) -> Optional[Page]:
        key = (table, page_id)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        page = self.disk.read_page(table, page_id)
        if page is None:
            return None
        self._admit(key, page)
        return page

    def new_page(self, table: str) -> Page:
        """Allocate a fresh page at the end of the table file."""
        page = self.disk.allocate_page(table)
        self._admit((table, page.page_id), page)
        return page

    def flush_page(self, table: str, page_id: int):
        key = (table, page_id)
        if key in self._cache:
            page = self._cache[key]
            if page.dirty:
                self.disk.write_page(table, page)
                page.dirty = False

    def flush_all(self):
        for (table, page_id), page in self._cache.items():
            if page.dirty:
                self.disk.write_page(table, page)
                page.dirty = False

    def evict_table(self, table: str):
        """Remove all cached pages for a table (used before truncation/drop)."""
        for key in [k for k in self._cache if k[0] == table]:
            del self._cache[key]

    # ── internals ─────────────────────────────────────────────────────────────

    def _admit(self, key: Tuple[str, int], page: Page):
        if len(self._cache) >= self.capacity:
            evict_key, evict_page = self._cache.popitem(last=False)
            if evict_page.dirty:
                self.disk.write_page(evict_key[0], evict_page)
        self._cache[key] = page
