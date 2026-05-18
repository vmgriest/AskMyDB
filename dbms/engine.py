from typing import Any

from .catalog.catalog import Catalog
from .sql.executor import DBError, Executor
from .sql.lexer import LexError, Lexer
from .sql.parser import ParseError, Parser
from .storage.buffer_pool import BufferPool
from .storage.disk_manager import DiskManager


class Engine:
    """Top-level entry point: SQL string → result."""

    def __init__(self, data_dir: str = "data"):
        self.catalog = Catalog(data_dir)
        disk = DiskManager(data_dir)
        self.pool = BufferPool(disk)
        self.executor = Executor(self.catalog, self.pool)

    def execute(self, sql: str) -> Any:
        try:
            tokens = Lexer(sql).tokenize()
            ast = Parser(tokens).parse()
            return self.executor.execute(ast)
        except (LexError, ParseError, DBError, KeyError, ValueError) as exc:
            return f"Error: {exc}"

    def close(self):
        self.pool.flush_all()
        self.pool.disk.close()
