import os
from typing import Optional

from .page import PAGE_SIZE, Page


class DiskManager:
    """Reads and writes pages to per-table binary files on disk."""

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)
        self._handles: dict = {}

    def _table_path(self, table: str) -> str:
        return os.path.join(self.db_dir, f"{table}.db")

    def _handle(self, table: str):
        if table not in self._handles:
            path = self._table_path(table)
            if not os.path.exists(path):
                open(path, "wb").close()
            self._handles[table] = open(path, "r+b")
        return self._handles[table]

    # ── page I/O ─────────────────────────────────────────────────────────────

    def read_page(self, table: str, page_id: int) -> Optional[Page]:
        fh = self._handle(table)
        offset = page_id * PAGE_SIZE
        fh.seek(0, 2)
        if offset >= fh.tell():
            return None
        fh.seek(offset)
        data = fh.read(PAGE_SIZE)
        if len(data) < PAGE_SIZE:
            return None
        return Page(page_id, data)

    def write_page(self, table: str, page: Page):
        fh = self._handle(table)
        fh.seek(page.page_id * PAGE_SIZE)
        fh.write(page.to_bytes())
        fh.flush()

    def allocate_page(self, table: str) -> Page:
        """Append a fresh page at the end of the table file."""
        fh = self._handle(table)
        fh.seek(0, 2)
        page_id = fh.tell() // PAGE_SIZE
        page = Page(page_id)
        self.write_page(table, page)
        return page

    # ── utilities ────────────────────────────────────────────────────────────

    def num_pages(self, table: str) -> int:
        path = self._table_path(table)
        if not os.path.exists(path):
            return 0
        return os.path.getsize(path) // PAGE_SIZE

    def close_table(self, table: str):
        """Close and forget the file handle for one table."""
        if table in self._handles:
            self._handles[table].close()
            del self._handles[table]

    def reset_table_file(self, table: str):
        """Close handle and truncate the table file to 0 bytes."""
        self.close_table(table)
        open(self._table_path(table), "wb").close()

    def delete_table_file(self, table: str):
        self.close_table(table)
        path = self._table_path(table)
        if os.path.exists(path):
            os.remove(path)

    def close(self):
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()
