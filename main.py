#!/usr/bin/env python3
"""AskMyDB — custom DBMS with an AI natural-language interface.

Usage:
  python main.py              # interactive SQL shell
  python main.py ai           # interactive AI (plain-English) shell
  python main.py ai llama3.2  # AI shell with a specific Ollama model
  python main.py "SELECT * FROM users"   # one-shot SQL from the command line
"""
import sys

from dbms.engine import Engine
from ai.translator import OllamaTranslator

DATA_DIR = "data"


# ── pretty-print query results ────────────────────────────────────────────────

def _fmt(result) -> str:
    if not isinstance(result, list):
        return str(result)
    if not result:
        return "(no rows)"
    headers = list(result[0].keys())
    widths = {
        h: max(len(h), max((len(str(r.get(h, ""))) for r in result), default=0))
        for h in headers
    }
    sep = "+" + "+".join("-" * (widths[h] + 2) for h in headers) + "+"
    hdr = "|" + "|".join(f" {h:<{widths[h]}} " for h in headers) + "|"
    lines = [sep, hdr, sep]
    for row in result:
        lines.append("|" + "|".join(f" {str(row.get(h, '')):<{widths[h]}} " for h in headers) + "|")
    lines.append(sep)
    return "\n".join(lines)


# ── SQL shell ─────────────────────────────────────────────────────────────────

def sql_shell(engine: Engine):
    print("AskMyDB SQL shell  —  type 'exit' or Ctrl-D to quit")
    print("Meta commands: .tables | .schema <table> | .mode ai\n")
    while True:
        try:
            line = input("sql> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line == ".tables":
            tables = engine.catalog.list_tables()
            print("\n".join(tables) if tables else "(no tables)")
            continue
        if line.startswith(".schema"):
            parts = line.split()
            if len(parts) == 2:
                try:
                    schema = engine.catalog.get_table(parts[1])
                    for c in schema.columns:
                        pk = "  PRIMARY KEY" if c.primary_key else ""
                        print(f"  {c.name:20} {c.col_type.value}{pk}")
                except KeyError as e:
                    print(f"Error: {e}")
            continue
        if line == ".mode ai":
            ai_shell(engine)
            continue
        print(_fmt(engine.execute(line)))


# ── AI shell ──────────────────────────────────────────────────────────────────

def ai_shell(engine: Engine, model: str = None):
    translator = OllamaTranslator(engine, model or OllamaTranslator.DEFAULT_MODEL)
    print(f"\nAskMyDB AI mode  (model: {translator.model})")
    print("Ask questions in plain English.  Type 'exit' or Ctrl-D to quit.")
    print("Type '.sql' to switch to SQL mode.\n")
    while True:
        try:
            question = input("ask> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break
        if question == ".sql":
            sql_shell(engine)
            continue

        print("  Thinking...", end="\r")
        out = translator.ask(question)
        pairs = out["results"]

        if len(pairs) == 1:
            sql, result = pairs[0]
            print(f"  SQL: {sql}")
            print(_fmt(result))
        else:
            # Multiple statements (e.g. "insert fake data" → several INSERTs)
            for i, (sql, result) in enumerate(pairs, 1):
                print(f"  [{i}] {sql}")
                print(f"      {_fmt(result)}")
        print()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    engine = Engine(DATA_DIR)
    try:
        if len(sys.argv) > 1:
            if sys.argv[1] == "ai":
                model = sys.argv[2] if len(sys.argv) > 2 else None
                ai_shell(engine, model)
            else:
                sql = " ".join(sys.argv[1:])
                print(_fmt(engine.execute(sql)))
        else:
            sql_shell(engine)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
