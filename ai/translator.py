import subprocess
from typing import Optional

from dbms.engine import Engine


class OllamaTranslator:
    """
    Translates plain-English questions into SQL using a local Ollama model,
    then executes the SQL against the custom DBMS.
    """

    DEFAULT_MODEL = "llama3.2"

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
        return f"""You are a SQL generator for AskMyDB, a custom database engine.

Database schema:
{self._schema_text()}

Supported SQL (use EXACTLY this syntax):
  SELECT [* | col, ...] FROM table [WHERE cond] [ORDER BY col [ASC|DESC]] [LIMIT n]
  INSERT INTO table [(col, ...)] VALUES (val, ...)
  CREATE TABLE table (col TYPE [PRIMARY KEY], ...)
  DROP TABLE table
  DELETE FROM table [WHERE cond]
  UPDATE table SET col=val [, ...] [WHERE cond]

WHERE operators: =  !=  <  >  <=  >=  AND  OR
Column types: INTEGER  FLOAT  STRING

User request: "{question}"

Reply with ONLY the SQL statement. No explanation. No markdown. No backticks."""

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

        # Fallback: call the ollama CLI
        try:
            result = subprocess.run(
                ["ollama", "run", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    # ── public API ────────────────────────────────────────────────────────────

    def translate(self, question: str) -> Optional[str]:
        """Return the SQL string for a plain-English question, or None on failure."""
        raw = self._call_ollama(self._prompt(question))
        if not raw:
            return None
        # Strip accidental markdown fences
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def ask(self, question: str) -> dict:
        """Full pipeline: English → SQL → execute → return result dict."""
        sql = self.translate(question)
        if not sql:
            return {
                "question": question,
                "sql": None,
                "result": "Could not generate SQL. Is Ollama running? (`ollama serve`)",
                "error": True,
            }
        result = self.engine.execute(sql)
        return {
            "question": question,
            "sql": sql,
            "result": result,
            "error": isinstance(result, str) and result.startswith("Error:"),
        }
