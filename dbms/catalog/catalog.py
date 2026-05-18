import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ColType(Enum):
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"


@dataclass
class Column:
    name: str
    col_type: ColType
    primary_key: bool = False


@dataclass
class TableSchema:
    name: str  # always lowercase
    columns: List[Column]

    def col_names(self) -> List[str]:
        return [c.name for c in self.columns]


class Catalog:
    """Persists and loads table schemas from a JSON catalog file."""

    _FILE = "catalog.json"

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)
        self._schemas: Dict[str, TableSchema] = {}
        self._load()

    def _path(self) -> str:
        return os.path.join(self.db_dir, self._FILE)

    def _load(self):
        if not os.path.exists(self._path()):
            return
        with open(self._path()) as f:
            data = json.load(f)
        for tname, tdata in data.items():
            cols = [
                Column(
                    name=c["name"],
                    col_type=ColType(c["type"]),
                    primary_key=c.get("primary_key", False),
                )
                for c in tdata["columns"]
            ]
            self._schemas[tname] = TableSchema(name=tname, columns=cols)

    def _save(self):
        data = {
            name: {
                "columns": [
                    {"name": c.name, "type": c.col_type.value, "primary_key": c.primary_key}
                    for c in schema.columns
                ]
            }
            for name, schema in self._schemas.items()
        }
        with open(self._path(), "w") as f:
            json.dump(data, f, indent=2)

    def create_table(self, schema: TableSchema):
        key = schema.name.lower()
        if key in self._schemas:
            raise ValueError(f"Table '{schema.name}' already exists")
        normalized = TableSchema(name=key, columns=schema.columns)
        self._schemas[key] = normalized
        self._save()

    def get_table(self, name: str) -> TableSchema:
        key = name.lower()
        if key not in self._schemas:
            raise KeyError(f"Table '{name}' does not exist")
        return self._schemas[key]

    def drop_table(self, name: str):
        key = name.lower()
        if key not in self._schemas:
            raise KeyError(f"Table '{name}' does not exist")
        del self._schemas[key]
        self._save()

    def list_tables(self) -> List[str]:
        return list(self._schemas.keys())

    def table_exists(self, name: str) -> bool:
        return name.lower() in self._schemas
