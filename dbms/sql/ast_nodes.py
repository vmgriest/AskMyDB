from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ColumnDef:
    name: str
    col_type: str  # "INTEGER", "FLOAT", "STRING"
    primary_key: bool = False


@dataclass
class CreateTableStmt:
    table: str
    columns: List[ColumnDef]


@dataclass
class DropTableStmt:
    table: str


class Expr:
    pass


@dataclass
class LiteralExpr(Expr):
    value: Any  # int, float, str, or None


@dataclass
class ColumnRef(Expr):
    column: str


@dataclass
class BinOp(Expr):
    op: str  # "=", "!=", "<", ">", "<=", ">=", "AND", "OR"
    left: Expr
    right: Expr


@dataclass
class SelectItem:
    expr: Optional[Expr]
    is_star: bool = False


@dataclass
class OrderByItem:
    column: str
    ascending: bool = True


@dataclass
class SelectStmt:
    table: str
    columns: List[SelectItem]
    where: Optional[Expr] = None
    order_by: List[OrderByItem] = field(default_factory=list)
    limit: Optional[int] = None


@dataclass
class InsertStmt:
    table: str
    col_names: Optional[List[str]]
    values: List[Any]


@dataclass
class DeleteStmt:
    table: str
    where: Optional[Expr]


@dataclass
class UpdateStmt:
    table: str
    assignments: List[tuple]  # [(col_name, value), ...]
    where: Optional[Expr]
