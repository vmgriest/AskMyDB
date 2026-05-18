import struct
from typing import Any, Dict, List, Optional

from ..catalog.catalog import Catalog, ColType, Column, TableSchema
from ..storage.buffer_pool import BufferPool
from .ast_nodes import (
    BinOp, ColumnRef, CreateTableStmt, DeleteStmt, DropTableStmt,
    Expr, InsertStmt, LiteralExpr, SelectStmt, UpdateStmt,
)


class DBError(Exception):
    pass


# ── record serialization ──────────────────────────────────────────────────────

def _serialize(schema: TableSchema, values: List[Any]) -> bytes:
    """Pack an ordered list of values into bytes."""
    parts = []
    for col, val in zip(schema.columns, values):
        if col.col_type == ColType.INTEGER:
            parts.append(struct.pack(">q", int(val) if val is not None else 0))
        elif col.col_type == ColType.FLOAT:
            parts.append(struct.pack(">d", float(val) if val is not None else 0.0))
        elif col.col_type == ColType.STRING:
            raw = (str(val) if val is not None else "").encode("utf-8")
            parts.append(struct.pack(">I", len(raw)) + raw)
    return b"".join(parts)


def _deserialize(schema: TableSchema, data: bytes) -> Dict[str, Any]:
    """Unpack bytes back into a {column_name: value} dict."""
    row: Dict[str, Any] = {}
    offset = 0
    for col in schema.columns:
        if col.col_type == ColType.INTEGER:
            row[col.name] = struct.unpack_from(">q", data, offset)[0]
            offset += 8
        elif col.col_type == ColType.FLOAT:
            row[col.name] = struct.unpack_from(">d", data, offset)[0]
            offset += 8
        elif col.col_type == ColType.STRING:
            length = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            row[col.name] = data[offset : offset + length].decode("utf-8")
            offset += length
    return row


# ── expression evaluator ──────────────────────────────────────────────────────

def _eval(expr: Expr, row: Dict[str, Any]) -> Any:
    if isinstance(expr, LiteralExpr):
        return expr.value
    if isinstance(expr, ColumnRef):
        col = expr.column.upper()
        for k, v in row.items():
            if k.upper() == col:
                return v
        raise DBError(f"Column '{expr.column}' not found")
    if isinstance(expr, BinOp):
        if expr.op == "AND":
            return bool(_eval(expr.left, row)) and bool(_eval(expr.right, row))
        if expr.op == "OR":
            return bool(_eval(expr.left, row)) or bool(_eval(expr.right, row))
        lv = _eval(expr.left, row)
        rv = _eval(expr.right, row)
        if expr.op == "=":  return lv == rv
        if expr.op == "!=": return lv != rv
        if expr.op == "<":  return lv < rv
        if expr.op == ">":  return lv > rv
        if expr.op == "<=": return lv <= rv
        if expr.op == ">=": return lv >= rv
        raise DBError(f"Unknown operator '{expr.op}'")
    raise DBError(f"Cannot evaluate {type(expr).__name__}")


# ── executor ──────────────────────────────────────────────────────────────────

class Executor:
    def __init__(self, catalog: Catalog, pool: BufferPool):
        self.catalog = catalog
        self.pool = pool

    def execute(self, stmt) -> Any:
        if isinstance(stmt, CreateTableStmt): return self._create(stmt)
        if isinstance(stmt, DropTableStmt):   return self._drop(stmt)
        if isinstance(stmt, InsertStmt):       return self._insert(stmt)
        if isinstance(stmt, SelectStmt):       return self._select(stmt)
        if isinstance(stmt, DeleteStmt):       return self._delete(stmt)
        if isinstance(stmt, UpdateStmt):       return self._update(stmt)
        raise DBError(f"Unknown statement type: {type(stmt).__name__}")

    # ── CREATE TABLE ──────────────────────────────────────────────────────────

    def _create(self, stmt: CreateTableStmt) -> str:
        cols = [
            Column(name=c.name, col_type=ColType(c.col_type), primary_key=c.primary_key)
            for c in stmt.columns
        ]
        schema = TableSchema(name=stmt.table.lower(), columns=cols)
        self.catalog.create_table(schema)
        page = self.pool.new_page(schema.name)
        self.pool.flush_page(schema.name, page.page_id)
        return f"Table '{schema.name}' created."

    # ── DROP TABLE ────────────────────────────────────────────────────────────

    def _drop(self, stmt: DropTableStmt) -> str:
        name = stmt.table.lower()
        self.catalog.drop_table(name)
        self.pool.evict_table(name)
        self.pool.disk.delete_table_file(name)
        return f"Table '{name}' dropped."

    # ── INSERT ────────────────────────────────────────────────────────────────

    def _insert(self, stmt: InsertStmt) -> str:
        schema = self.catalog.get_table(stmt.table)
        name = schema.name

        if stmt.col_names:
            by_col = {c.upper(): v for c, v in zip(stmt.col_names, stmt.values)}
            values = [by_col.get(col.name.upper()) for col in schema.columns]
        else:
            if len(stmt.values) != len(schema.columns):
                raise DBError(
                    f"Expected {len(schema.columns)} values, got {len(stmt.values)}"
                )
            values = stmt.values

        record = _serialize(schema, values)
        self._append_record(name, record)
        return "1 row inserted."

    def _append_record(self, name: str, record: bytes):
        for pid in range(self.pool.disk.num_pages(name)):
            page = self.pool.fetch_page(name, pid)
            if page and page.insert_record(record) is not None:
                self.pool.flush_page(name, pid)
                return
        page = self.pool.new_page(name)
        page.insert_record(record)
        self.pool.flush_page(name, page.page_id)

    # ── full-table scan ───────────────────────────────────────────────────────

    def _scan(self, table_name: str) -> List[Dict[str, Any]]:
        schema = self.catalog.get_table(table_name)
        name = schema.name
        rows = []
        for pid in range(self.pool.disk.num_pages(name)):
            page = self.pool.fetch_page(name, pid)
            if page:
                for rec in page.get_records():
                    rows.append(_deserialize(schema, rec))
        return rows

    # ── SELECT ────────────────────────────────────────────────────────────────

    def _select(self, stmt: SelectStmt) -> List[Dict[str, Any]]:
        rows = self._scan(stmt.table)

        if stmt.where:
            rows = [r for r in rows if _eval(stmt.where, r)]

        all_star = any(item.is_star for item in stmt.columns)
        if not all_star:
            wanted = {
                item.expr.column.upper()
                for item in stmt.columns
                if isinstance(item.expr, ColumnRef)
            }
            rows = [{k: v for k, v in r.items() if k.upper() in wanted} for r in rows]

        for ob in reversed(stmt.order_by):
            col = ob.column.upper()
            rows.sort(
                key=lambda r: next((v for k, v in r.items() if k.upper() == col), None),
                reverse=not ob.ascending,
            )

        if stmt.limit is not None:
            rows = rows[: stmt.limit]

        return rows

    # ── DELETE ────────────────────────────────────────────────────────────────

    def _delete(self, stmt: DeleteStmt) -> str:
        schema = self.catalog.get_table(stmt.table)
        rows = self._scan(stmt.table)
        keep = [r for r in rows if not (stmt.where and _eval(stmt.where, r))]
        deleted = len(rows) - len(keep)
        self._rewrite(schema, keep)
        return f"{deleted} row(s) deleted."

    # ── UPDATE ────────────────────────────────────────────────────────────────

    def _update(self, stmt: UpdateStmt) -> str:
        schema = self.catalog.get_table(stmt.table)
        rows = self._scan(stmt.table)
        updated = 0
        new_rows = []
        for row in rows:
            if stmt.where is None or _eval(stmt.where, row):
                row = dict(row)
                for col_name, val in stmt.assignments:
                    for col in schema.columns:
                        if col.name.upper() == col_name.upper():
                            row[col.name] = val
                            break
                updated += 1
            new_rows.append(row)
        self._rewrite(schema, new_rows)
        return f"{updated} row(s) updated."

    # ── rewrite ───────────────────────────────────────────────────────────────

    def _rewrite(self, schema: TableSchema, rows: List[Dict[str, Any]]):
        """Truncate the table file and write back the given rows."""
        name = schema.name
        self.pool.evict_table(name)
        self.pool.disk.reset_table_file(name)
        for row in rows:
            values = [row.get(col.name) for col in schema.columns]
            self._append_record(name, _serialize(schema, values))
        if self.pool.disk.num_pages(name) == 0:
            page = self.pool.new_page(name)
            self.pool.flush_page(name, page.page_id)
