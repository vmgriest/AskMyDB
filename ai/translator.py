import re
import subprocess
from typing import List, Optional

from dbms.engine import Engine


class OllamaTranslator:
    """
    Translates plain-English questions into SQL using a local Ollama model,
    then executes the SQL against the custom DBMS.
    """

    DEFAULT_MODEL = "llama3.2"

    # Only statement-opening keywords — used to find statement boundaries
    _STMT_KW = {"SELECT", "INSERT", "CREATE", "DROP", "DELETE", "UPDATE"}
    _STMT_RE = re.compile(r"\b(SELECT|INSERT|CREATE|DROP|DELETE|UPDATE)\b", re.IGNORECASE)

    def __init__(self, engine: Engine, model: str = DEFAULT_MODEL):
        self.engine = engine
        self.model = model

    # ── schema context ────────────────────────────────────────────────────────

    def _schema_text(self) -> str:
        tables = self.engine.catalog.list_tables()
        if not tables:
            return "  (no tables exist yet)"
        lines = []
        for name in tables:
            schema = self.engine.catalog.get_table(name)
            col_parts = ", ".join(
                f"{c.name} {c.col_type.value}" + (" PK" if c.primary_key else "")
                for c in schema.columns
            )
            lines.append(f"  {name}({col_parts})")
        return "\n".join(lines)

    # ── prompt ────────────────────────────────────────────────────────────────

    def _prompt(self, question: str) -> str:
        return f"""You are a SQL generator for AskMyDB, a minimal custom database engine.

Database schema:
{self._schema_text()}

SUPPORTED syntax:
  SELECT [* | col, ...] FROM table [WHERE cond] [ORDER BY col [ASC|DESC]] [LIMIT n]
  INSERT INTO table [(col, ...)] VALUES (val, ...)
  CREATE TABLE table (col TYPE [PRIMARY KEY], ...)
  DROP TABLE table
  DELETE FROM table [WHERE cond]
  UPDATE table SET col=val [, ...] [WHERE cond]

WHERE operators: =  !=  <  >  <=  >=  AND  OR
Column types: INTEGER  FLOAT  STRING

NOT SUPPORTED — never use any of these:
  - SQL functions: LOWER(), UPPER(), RAND(), COUNT(), SUM(), SUBSTR(), REPEAT(), etc.
  - Arithmetic or string expressions: x+1, x*2, 'a'||'b'
  - Subqueries, JOINs, GROUP BY, HAVING, OVER()
  - NULL as a value — use 0, 0.0, or '' instead

VALUES must be plain literals only:  42   3.14   'hello world'

For "insert fake/sample data" requests: generate several INSERT statements with
hardcoded literal values (no functions), one per line, each ending with a semicolon.

User request: "{question}"

Respond with ONLY SQL. No explanation, no markdown, no backticks.
Each statement must end with a semicolon."""

    # ── Ollama call ───────────────────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> Optional[str]:
        try:
            import ollama  # type: ignore
            resp = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            return resp["message"]["content"].strip()
        except ImportError:
            pass

        # Fallback: call the ollama CLI  (run `pip install ollama` to skip this path)
        try:
            result = subprocess.run(
                ["ollama", "run", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",   # never crash on non-UTF-8 bytes from the CLI
                timeout=60,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired, UnicodeDecodeError):
            return None

    # ── SQL extraction ────────────────────────────────────────────────────────

    def _extract_statements(self, raw: str) -> List[str]:
        """
        Parse raw LLM output into a list of clean SQL statements.

        Handles:
        - Markdown fences
        - Curly/smart quotes
        - Multiple statements on one line (no semicolons)
        - Extra explanatory text before/after the SQL
        """
        lines = raw.splitlines()

        # Strip markdown fences
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        # Collapse to a single string and normalise smart quotes
        text = " ".join(lines)
        for curly, straight in [("‘", "'"), ("’", "'"),
                                  ("“", "'"), ("”", "'")]:
            text = text.replace(curly, straight)

        # Split on explicit semicolons first
        parts = [p.strip() for p in text.split(";") if p.strip()]

        statements: List[str] = []
        for part in parts:
            if not part.split():
                continue

            # Always split by statement-keyword boundaries within the part.
            # This handles both "normal" parts and LLM responses that glued two
            # statements together without a semicolon.
            matches = list(self._STMT_RE.finditer(part))
            if not matches:
                continue
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(part)
                segment = part[m.start():end].strip()
                if segment and segment.split()[0].upper() in self._STMT_KW:
                    statements.append(segment)

        return statements

    # ── public API ────────────────────────────────────────────────────────────

    def translate(self, question: str) -> Optional[str]:
        """Return the first SQL statement for a plain-English question."""
        raw = self._call_ollama(self._prompt(question))
        if not raw:
            return None
        stmts = self._extract_statements(raw)
        return stmts[0] if stmts else None

    def ask(self, question: str) -> dict:
        """
        Full pipeline: English → SQL → execute all statements → return results.

        Returns a dict with:
          sql      — the SQL string(s) that were generated (joined by newline)
          results  — list of (sql_stmt, result) pairs
          error    — True if any statement returned an error
        """
        raw = self._call_ollama(self._prompt(question))
        if not raw:
            return {
                "question": question,
                "sql": None,
                "results": [(None, "Could not generate SQL — is Ollama running? (`ollama serve`)")]
            }

        stmts = self._extract_statements(raw)
        if not stmts:
            return {
                "question": question,
                "sql": raw,
                "results": [(raw, "Could not extract a valid SQL statement from the response.")]
            }

        pairs = [(s, self.engine.execute(s)) for s in stmts]
        return {
            "question": question,
            "sql": ";\n".join(stmts),
            "results": pairs,
            "error": any(isinstance(r, str) and r.startswith("Error:") for _, r in pairs),
        }
