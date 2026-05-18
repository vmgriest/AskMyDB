from typing import List, Optional

from .ast_nodes import (
    BinOp, ColumnDef, ColumnRef, CreateTableStmt, DeleteStmt,
    DropTableStmt, InsertStmt, LiteralExpr, OrderByItem,
    SelectItem, SelectStmt, UpdateStmt,
)
from .lexer import TT, Token


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # ── token helpers ─────────────────────────────────────────────────────────

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, tt: TT) -> Token:
        tok = self._advance()
        if tok.type != tt:
            raise ParseError(f"Expected {tt.name}, got {tok.type.name} ({tok.value!r})")
        return tok

    def _match(self, *types: TT) -> bool:
        return self._peek().type in types

    def _consume(self, *types: TT) -> Optional[Token]:
        if self._match(*types):
            return self._advance()
        return None

    # ── entry point ───────────────────────────────────────────────────────────

    def parse(self):
        stmt = self._statement()
        self._consume(TT.SEMICOLON)
        if not self._match(TT.EOF):
            raise ParseError(f"Unexpected token after statement: {self._peek()}")
        return stmt

    def _statement(self):
        t = self._peek().type
        if t == TT.SELECT:
            return self._select()
        if t == TT.INSERT:
            return self._insert()
        if t == TT.CREATE:
            return self._create()
        if t == TT.DROP:
            return self._drop()
        if t == TT.DELETE:
            return self._delete()
        if t == TT.UPDATE:
            return self._update()
        raise ParseError(f"Unknown statement starting with {self._peek()}")

    # ── SELECT ────────────────────────────────────────────────────────────────

    def _select(self) -> SelectStmt:
        self._expect(TT.SELECT)

        columns: List[SelectItem] = []
        if self._match(TT.STAR):
            self._advance()
            columns.append(SelectItem(expr=None, is_star=True))
        else:
            columns.append(SelectItem(expr=self._expr()))
            while self._consume(TT.COMMA):
                columns.append(SelectItem(expr=self._expr()))

        self._expect(TT.FROM)
        table = self._expect(TT.IDENT).value

        where = None
        if self._consume(TT.WHERE):
            where = self._expr()

        order_by: List[OrderByItem] = []
        if self._consume(TT.ORDER):
            self._expect(TT.BY)
            order_by.append(self._order_item())
            while self._consume(TT.COMMA):
                order_by.append(self._order_item())

        limit = None
        if self._consume(TT.LIMIT):
            limit = self._expect(TT.INT_LIT).value

        return SelectStmt(table=table, columns=columns, where=where,
                          order_by=order_by, limit=limit)

    def _order_item(self) -> OrderByItem:
        col = self._expect(TT.IDENT).value
        ascending = True
        if self._consume(TT.DESC):
            ascending = False
        else:
            self._consume(TT.ASC)
        return OrderByItem(column=col, ascending=ascending)

    # ── INSERT ────────────────────────────────────────────────────────────────

    def _insert(self) -> InsertStmt:
        self._expect(TT.INSERT)
        self._expect(TT.INTO)
        table = self._expect(TT.IDENT).value

        col_names = None
        if self._consume(TT.LPAREN):
            col_names = [self._expect(TT.IDENT).value]
            while self._consume(TT.COMMA):
                col_names.append(self._expect(TT.IDENT).value)
            self._expect(TT.RPAREN)

        self._expect(TT.VALUES)
        self._expect(TT.LPAREN)
        values = [self._literal()]
        while self._consume(TT.COMMA):
            values.append(self._literal())
        self._expect(TT.RPAREN)

        return InsertStmt(table=table, col_names=col_names, values=values)

    # ── CREATE TABLE ──────────────────────────────────────────────────────────

    def _create(self) -> CreateTableStmt:
        self._expect(TT.CREATE)
        self._expect(TT.TABLE)
        table = self._expect(TT.IDENT).value
        self._expect(TT.LPAREN)

        cols = [self._col_def()]
        while self._consume(TT.COMMA):
            cols.append(self._col_def())
        self._expect(TT.RPAREN)

        return CreateTableStmt(table=table, columns=cols)

    def _col_def(self) -> ColumnDef:
        name = self._expect(TT.IDENT).value
        type_tok = self._advance()
        if type_tok.type == TT.INTEGER:
            col_type = "INTEGER"
        elif type_tok.type == TT.FLOAT:
            col_type = "FLOAT"
        elif type_tok.type in (TT.STRING, TT.TEXT):
            col_type = "STRING"
        else:
            raise ParseError(f"Unknown column type '{type_tok.value}'")

        is_pk = False
        if self._consume(TT.PRIMARY):
            self._expect(TT.KEY)
            is_pk = True

        return ColumnDef(name=name, col_type=col_type, primary_key=is_pk)

    # ── DROP TABLE ────────────────────────────────────────────────────────────

    def _drop(self) -> DropTableStmt:
        self._expect(TT.DROP)
        self._expect(TT.TABLE)
        return DropTableStmt(table=self._expect(TT.IDENT).value)

    # ── DELETE ────────────────────────────────────────────────────────────────

    def _delete(self) -> DeleteStmt:
        self._expect(TT.DELETE)
        self._expect(TT.FROM)
        table = self._expect(TT.IDENT).value
        where = None
        if self._consume(TT.WHERE):
            where = self._expr()
        return DeleteStmt(table=table, where=where)

    # ── UPDATE ────────────────────────────────────────────────────────────────

    def _update(self) -> UpdateStmt:
        self._expect(TT.UPDATE)
        table = self._expect(TT.IDENT).value
        self._expect(TT.SET)

        def _assignment():
            col = self._expect(TT.IDENT).value
            self._expect(TT.EQ)
            val = self._literal()
            return (col, val)

        assignments = [_assignment()]
        while self._consume(TT.COMMA):
            assignments.append(_assignment())

        where = None
        if self._consume(TT.WHERE):
            where = self._expr()

        return UpdateStmt(table=table, assignments=assignments, where=where)

    # ── expressions ───────────────────────────────────────────────────────────

    def _expr(self):
        return self._or()

    def _or(self):
        left = self._and()
        while self._consume(TT.OR):
            right = self._and()
            left = BinOp(op="OR", left=left, right=right)
        return left

    def _and(self):
        left = self._comparison()
        while self._consume(TT.AND):
            right = self._comparison()
            left = BinOp(op="AND", left=left, right=right)
        return left

    _CMP_OPS = {TT.EQ: "=", TT.NEQ: "!=", TT.LT: "<",
                TT.GT: ">", TT.LTE: "<=", TT.GTE: ">="}

    def _comparison(self):
        left = self._primary()
        if self._peek().type in self._CMP_OPS:
            op = self._CMP_OPS[self._advance().type]
            right = self._primary()
            return BinOp(op=op, left=left, right=right)
        return left

    def _primary(self):
        tok = self._peek()
        if tok.type in (TT.INT_LIT, TT.FLOAT_LIT, TT.STR_LIT):
            return LiteralExpr(value=self._advance().value)
        if tok.type == TT.NULL:
            self._advance()
            return LiteralExpr(value=None)
        if tok.type == TT.IDENT:
            return ColumnRef(column=self._advance().value)
        if tok.type == TT.LPAREN:
            self._advance()
            expr = self._expr()
            self._expect(TT.RPAREN)
            return expr
        raise ParseError(f"Unexpected token in expression: {tok}")

    def _literal(self):
        tok = self._peek()
        if tok.type == TT.INT_LIT:
            return self._advance().value
        if tok.type == TT.FLOAT_LIT:
            return self._advance().value
        if tok.type == TT.STR_LIT:
            return self._advance().value
        if tok.type == TT.NULL:
            self._advance()
            return None
        raise ParseError(f"Expected a literal value, got {tok}")
