from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TT(Enum):
    # Keywords
    SELECT = auto(); FROM = auto(); WHERE = auto()
    INSERT = auto(); INTO = auto(); VALUES = auto()
    CREATE = auto(); TABLE = auto(); DROP = auto()
    DELETE = auto(); UPDATE = auto(); SET = auto()
    AND = auto(); OR = auto(); NOT = auto(); NULL = auto()
    ORDER = auto(); BY = auto(); ASC = auto(); DESC = auto()
    LIMIT = auto(); PRIMARY = auto(); KEY = auto()
    INTEGER = auto(); FLOAT = auto(); STRING = auto(); TEXT = auto()
    # Punctuation
    STAR = auto(); COMMA = auto(); SEMICOLON = auto()
    LPAREN = auto(); RPAREN = auto()
    # Comparison
    EQ = auto(); NEQ = auto(); LT = auto(); GT = auto()
    LTE = auto(); GTE = auto()
    # Literals / identifiers
    IDENT = auto()
    INT_LIT = auto()
    FLOAT_LIT = auto()
    STR_LIT = auto()
    EOF = auto()


_KW: dict = {
    "SELECT": TT.SELECT, "FROM": TT.FROM, "WHERE": TT.WHERE,
    "INSERT": TT.INSERT, "INTO": TT.INTO, "VALUES": TT.VALUES,
    "CREATE": TT.CREATE, "TABLE": TT.TABLE, "DROP": TT.DROP,
    "DELETE": TT.DELETE, "UPDATE": TT.UPDATE, "SET": TT.SET,
    "AND": TT.AND, "OR": TT.OR, "NOT": TT.NOT, "NULL": TT.NULL,
    "ORDER": TT.ORDER, "BY": TT.BY, "ASC": TT.ASC, "DESC": TT.DESC,
    "LIMIT": TT.LIMIT, "PRIMARY": TT.PRIMARY, "KEY": TT.KEY,
    "INTEGER": TT.INTEGER, "INT": TT.INTEGER,
    "FLOAT": TT.FLOAT, "DOUBLE": TT.FLOAT,
    "STRING": TT.STRING, "TEXT": TT.TEXT, "VARCHAR": TT.STRING,
}


@dataclass
class Token:
    type: TT
    value: object

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r})"


class LexError(Exception):
    pass


class Lexer:
    def __init__(self, sql: str):
        self.src = sql
        self.pos = 0

    def _peek(self) -> str:
        return self.src[self.pos] if self.pos < len(self.src) else ""

    def _next(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        return ch

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while self.pos < len(self.src):
            ch = self._peek()

            if ch.isspace():
                self.pos += 1

            elif ch == "-" and self.pos + 1 < len(self.src) and self.src[self.pos + 1] == "-":
                while self.pos < len(self.src) and self.src[self.pos] != "\n":
                    self.pos += 1

            elif ch == "*":
                tokens.append(Token(TT.STAR, "*")); self.pos += 1
            elif ch == ",":
                tokens.append(Token(TT.COMMA, ",")); self.pos += 1
            elif ch == ";":
                tokens.append(Token(TT.SEMICOLON, ";")); self.pos += 1
            elif ch == "(":
                tokens.append(Token(TT.LPAREN, "(")); self.pos += 1
            elif ch == ")":
                tokens.append(Token(TT.RPAREN, ")")); self.pos += 1

            elif ch == "=":
                self.pos += 1
                tokens.append(Token(TT.EQ, "="))
            elif ch == "!":
                self.pos += 1
                if self._peek() == "=":
                    self.pos += 1
                    tokens.append(Token(TT.NEQ, "!="))
                else:
                    raise LexError(f"Unexpected '!' at position {self.pos}")
            elif ch == "<":
                self.pos += 1
                if self._peek() == "=":
                    self.pos += 1
                    tokens.append(Token(TT.LTE, "<="))
                elif self._peek() == ">":
                    self.pos += 1
                    tokens.append(Token(TT.NEQ, "<>"))
                else:
                    tokens.append(Token(TT.LT, "<"))
            elif ch == ">":
                self.pos += 1
                if self._peek() == "=":
                    self.pos += 1
                    tokens.append(Token(TT.GTE, ">="))
                else:
                    tokens.append(Token(TT.GT, ">"))

            elif ch == "'":
                self.pos += 1
                start = self.pos
                while self.pos < len(self.src) and self.src[self.pos] != "'":
                    self.pos += 1
                if self.pos >= len(self.src):
                    raise LexError("Unterminated string literal")
                val = self.src[start : self.pos]
                self.pos += 1
                tokens.append(Token(TT.STR_LIT, val))

            elif ch.isdigit():
                start = self.pos
                while self._peek().isdigit():
                    self.pos += 1
                if self._peek() == "." and self.pos + 1 < len(self.src) and self.src[self.pos + 1].isdigit():
                    self.pos += 1
                    while self._peek().isdigit():
                        self.pos += 1
                    tokens.append(Token(TT.FLOAT_LIT, float(self.src[start : self.pos])))
                else:
                    tokens.append(Token(TT.INT_LIT, int(self.src[start : self.pos])))

            elif ch == "-" and self.pos + 1 < len(self.src) and self.src[self.pos + 1].isdigit():
                start = self.pos
                self.pos += 1
                while self._peek().isdigit():
                    self.pos += 1
                if self._peek() == "." and self.pos + 1 < len(self.src) and self.src[self.pos + 1].isdigit():
                    self.pos += 1
                    while self._peek().isdigit():
                        self.pos += 1
                    tokens.append(Token(TT.FLOAT_LIT, float(self.src[start : self.pos])))
                else:
                    tokens.append(Token(TT.INT_LIT, int(self.src[start : self.pos])))

            elif ch.isalpha() or ch == "_":
                start = self.pos
                while self._peek().isalnum() or self._peek() == "_":
                    self.pos += 1
                word = self.src[start : self.pos]
                tt = _KW.get(word.upper(), TT.IDENT)
                tokens.append(Token(tt, word))

            else:
                raise LexError(f"Unexpected character '{ch}' at position {self.pos}")

        tokens.append(Token(TT.EOF, None))
        return tokens
