"""
SQLite-backed Supabase-compatible client.

Supports the chain used throughout the app:
  client.table("name").select("*").eq("id", x).order(...).limit(...).execute()
  .insert(data).execute()
  .update(data).eq(...).execute()
  .delete().eq(...).execute()
  .upsert(data).execute()
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from local.constants import DB_PATH, LOCAL_USER_ID, LOCAL_USER_EMAIL, LOCAL_USER_NAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# Columns that are stored as JSON text
JSON_COLUMNS = {
    "processing_options", "draft_data", "voice_settings", "audio_settings",
    "caption_settings", "word_segments", "music_settings", "additional_options",
    "old_value", "new_value", "character_ids", "dialogue_turns", "character_layout",
    "generated_image", "animated_video", "scene_audio", "layer_data", "tags",
    "reference_image_ids", "metadata", "project_tags", "result",
}


class QueryResult:
    def __init__(self, data: Any = None, count: Optional[int] = None):
        self.data = data
        self.count = count


class TableQuery:
    def __init__(self, db: "LocalDatabase", table: str):
        self.db = db
        self.table = table
        self._action = "select"
        self._select_cols = "*"
        self._filters: List[tuple] = []
        self._order: List[tuple] = []
        self._limit_n: Optional[int] = None
        self._offset_n: Optional[int] = None
        self._payload: Any = None
        self._upsert_on: Optional[str] = None
        self._single = False
        self._maybe_single = False

    def select(self, columns: str = "*", count: Optional[str] = None) -> "TableQuery":
        self._action = "select"
        self._select_cols = columns
        return self

    def insert(self, data: Union[Dict, List[Dict]]) -> "TableQuery":
        self._action = "insert"
        self._payload = data
        return self

    def update(self, data: Dict) -> "TableQuery":
        self._action = "update"
        self._payload = data
        return self

    def delete(self) -> "TableQuery":
        self._action = "delete"
        return self

    def upsert(self, data: Union[Dict, List[Dict]], on_conflict: str = "id") -> "TableQuery":
        self._action = "upsert"
        self._payload = data
        self._upsert_on = on_conflict
        return self

    def eq(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("neq", column, value))
        return self

    def gt(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("gt", column, value))
        return self

    def gte(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("gte", column, value))
        return self

    def lt(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("lt", column, value))
        return self

    def lte(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("lte", column, value))
        return self

    def like(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("like", column, value))
        return self

    def ilike(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("ilike", column, value))
        return self

    def in_(self, column: str, values: List[Any]) -> "TableQuery":
        self._filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: Any) -> "TableQuery":
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, desc: bool = False, foreign_table: Optional[str] = None) -> "TableQuery":
        self._order.append((column, desc))
        return self

    def limit(self, n: int) -> "TableQuery":
        self._limit_n = n
        return self

    def offset(self, n: int) -> "TableQuery":
        self._offset_n = n
        return self

    def single(self) -> "TableQuery":
        self._single = True
        self._limit_n = 1
        return self

    def maybe_single(self) -> "TableQuery":
        self._maybe_single = True
        self._limit_n = 1
        return self

    def range(self, start: int, end: int) -> "TableQuery":
        self._offset_n = start
        self._limit_n = end - start + 1
        return self

    def execute(self) -> QueryResult:
        with self.db.lock:
            conn = self.db.connection()
            try:
                if self._action == "select":
                    return self._do_select(conn)
                if self._action == "insert":
                    return self._do_insert(conn)
                if self._action == "update":
                    return self._do_update(conn)
                if self._action == "delete":
                    return self._do_delete(conn)
                if self._action == "upsert":
                    return self._do_upsert(conn)
                raise ValueError(f"Unknown action: {self._action}")
            finally:
                conn.commit()

    def _where_clause(self) -> tuple[str, list]:
        if not self._filters:
            return "", []
        parts = []
        params: list = []
        for op, col, val in self._filters:
            if op == "eq":
                parts.append(f'"{col}" = ?')
                params.append(self._encode(col, val))
            elif op == "neq":
                parts.append(f'"{col}" != ?')
                params.append(self._encode(col, val))
            elif op == "gt":
                parts.append(f'"{col}" > ?')
                params.append(val)
            elif op == "gte":
                parts.append(f'"{col}" >= ?')
                params.append(val)
            elif op == "lt":
                parts.append(f'"{col}" < ?')
                params.append(val)
            elif op == "lte":
                parts.append(f'"{col}" <= ?')
                params.append(val)
            elif op == "like":
                parts.append(f'"{col}" LIKE ?')
                params.append(val)
            elif op == "ilike":
                parts.append(f'LOWER("{col}") LIKE LOWER(?)')
                params.append(val)
            elif op == "in":
                placeholders = ",".join("?" for _ in val)
                parts.append(f'"{col}" IN ({placeholders})')
                params.extend([self._encode(col, v) for v in val])
            elif op == "is":
                if val is None:
                    parts.append(f'"{col}" IS NULL')
                else:
                    parts.append(f'"{col}" = ?')
                    params.append(self._encode(col, val))
        return " WHERE " + " AND ".join(parts), params

    def _encode(self, col: str, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        if col in JSON_COLUMNS and not isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, bool):
            return 1 if value else 0
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value) if not isinstance(value, (int, float, str, bytes)) else value

    def _decode_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for k, v in list(d.items()):
            if v is None:
                continue
            if k in JSON_COLUMNS and isinstance(v, str):
                try:
                    d[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def _ensure_columns(self, conn: sqlite3.Connection, data: Dict) -> None:
        """Dynamically add missing columns as TEXT for flexibility."""
        existing = {
            r[1] for r in conn.execute(f'PRAGMA table_info("{self.table}")').fetchall()
        }
        for key in data.keys():
            if key not in existing:
                try:
                    conn.execute(f'ALTER TABLE "{self.table}" ADD COLUMN "{key}" TEXT')
                except sqlite3.OperationalError:
                    pass

    def _do_select(self, conn: sqlite3.Connection) -> QueryResult:
        # Strip join syntax like "col1, other_table(cols)" — only keep simple cols
        cols = self._select_cols
        if "(" in cols:
            # Simplified: select * when joins requested
            cols = "*"
        where, params = self._where_clause()
        sql = f'SELECT {cols} FROM "{self.table}"{where}'
        if self._order:
            order_bits = []
            for col, desc in self._order:
                order_bits.append(f'"{col}" {"DESC" if desc else "ASC"}')
            sql += " ORDER BY " + ", ".join(order_bits)
        if self._limit_n is not None:
            sql += f" LIMIT {int(self._limit_n)}"
        if self._offset_n is not None:
            sql += f" OFFSET {int(self._offset_n)}"
        try:
            cur = conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            # Table might not exist yet
            if "no such table" in str(e).lower():
                return QueryResult(data=[] if not self._single else None)
            raise
        rows = [self._decode_row(r) for r in cur.fetchall()]
        if self._single:
            if not rows:
                raise Exception(f"No rows found in {self.table}")
            return QueryResult(data=rows[0])
        if self._maybe_single:
            return QueryResult(data=rows[0] if rows else None)
        return QueryResult(data=rows, count=len(rows))

    def _do_insert(self, conn: sqlite3.Connection) -> QueryResult:
        items = self._payload if isinstance(self._payload, list) else [self._payload]
        results = []
        for item in items:
            data = dict(item)
            if "id" not in data or data["id"] is None:
                data["id"] = _new_id()
            else:
                data["id"] = str(data["id"])
            if "created_at" not in data or data["created_at"] is None:
                data["created_at"] = _now()
            if "updated_at" not in data:
                data["updated_at"] = _now()
            self._ensure_columns(conn, data)
            cols = list(data.keys())
            placeholders = ",".join("?" for _ in cols)
            col_sql = ",".join(f'"{c}"' for c in cols)
            values = [self._encode(c, data[c]) for c in cols]
            conn.execute(
                f'INSERT INTO "{self.table}" ({col_sql}) VALUES ({placeholders})',
                values,
            )
            results.append(self._fetch_by_id(conn, data["id"]) or data)
        return QueryResult(data=results if isinstance(self._payload, list) else results)

    def _do_update(self, conn: sqlite3.Connection) -> QueryResult:
        data = dict(self._payload)
        data["updated_at"] = _now()
        self._ensure_columns(conn, data)
        where, params = self._where_clause()
        if not where:
            raise ValueError("Update requires a filter (eq/...)")
        sets = []
        set_params = []
        for k, v in data.items():
            sets.append(f'"{k}" = ?')
            set_params.append(self._encode(k, v))
        sql = f'UPDATE "{self.table}" SET {", ".join(sets)}{where}'
        conn.execute(sql, set_params + params)
        # Return updated rows
        return self._do_select(conn)

    def _do_delete(self, conn: sqlite3.Connection) -> QueryResult:
        where, params = self._where_clause()
        # Fetch first for return
        before = self._do_select(conn)
        sql = f'DELETE FROM "{self.table}"{where}'
        conn.execute(sql, params)
        return before

    def _do_upsert(self, conn: sqlite3.Connection) -> QueryResult:
        items = self._payload if isinstance(self._payload, list) else [self._payload]
        results = []
        conflict_key = self._upsert_on or "id"
        for item in items:
            data = dict(item)
            if conflict_key not in data or data[conflict_key] is None:
                data["id"] = data.get("id") or _new_id()
            key_val = str(data[conflict_key])
            existing = conn.execute(
                f'SELECT id FROM "{self.table}" WHERE "{conflict_key}" = ?',
                (key_val,),
            ).fetchone()
            if existing:
                # update
                data["updated_at"] = _now()
                self._ensure_columns(conn, data)
                sets = []
                params = []
                for k, v in data.items():
                    if k == conflict_key:
                        continue
                    sets.append(f'"{k}" = ?')
                    params.append(self._encode(k, v))
                if sets:
                    conn.execute(
                        f'UPDATE "{self.table}" SET {", ".join(sets)} WHERE "{conflict_key}" = ?',
                        params + [key_val],
                    )
                results.append(self._fetch_by_id(conn, data.get("id") or key_val) or data)
            else:
                if "id" not in data or data["id"] is None:
                    data["id"] = _new_id()
                if "created_at" not in data:
                    data["created_at"] = _now()
                data["updated_at"] = _now()
                self._ensure_columns(conn, data)
                cols = list(data.keys())
                placeholders = ",".join("?" for _ in cols)
                col_sql = ",".join(f'"{c}"' for c in cols)
                values = [self._encode(c, data[c]) for c in cols]
                conn.execute(
                    f'INSERT INTO "{self.table}" ({col_sql}) VALUES ({placeholders})',
                    values,
                )
                results.append(self._fetch_by_id(conn, data["id"]) or data)
        return QueryResult(data=results if isinstance(self._payload, list) else results)

    def _fetch_by_id(self, conn: sqlite3.Connection, row_id: str) -> Optional[Dict]:
        try:
            cur = conn.execute(f'SELECT * FROM "{self.table}" WHERE id = ?', (str(row_id),))
            row = cur.fetchone()
            return self._decode_row(row) if row else None
        except sqlite3.OperationalError:
            return None


class LocalDatabase:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()
        self._seed_local_user()

    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text()
        conn = self.connection()
        conn.executescript(sql)
        conn.commit()

    def _seed_local_user(self) -> None:
        conn = self.connection()
        existing = conn.execute(
            "SELECT id FROM users WHERE id = ?", (LOCAL_USER_ID,)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO users (id, email, first_name, type, has_watched_tutorial, created_at, updated_at, email_confirmed_at)
                   VALUES (?, ?, ?, 'local', 1, ?, ?, ?)""",
                (LOCAL_USER_ID, LOCAL_USER_EMAIL, LOCAL_USER_NAME, _now(), _now(), _now()),
            )
            conn.commit()

    def table(self, name: str) -> TableQuery:
        return TableQuery(self, name)

    # Auth-like stub for code that calls supabase.auth
    @property
    def auth(self):
        return _AuthStub()

    @property
    def storage(self):
        return _StorageStub()


class _AuthStub:
    def get_user(self, *args, **kwargs):
        class U:
            user = type("User", (), {
                "id": LOCAL_USER_ID,
                "email": LOCAL_USER_EMAIL,
                "user_metadata": {"name": LOCAL_USER_NAME},
            })()
        return U()

    def get_session(self, *args, **kwargs):
        return None

    def sign_in_with_password(self, *args, **kwargs):
        return self.get_user()

    def sign_out(self, *args, **kwargs):
        return None


class _StorageStub:
    def from_(self, *args, **kwargs):
        return self

    def upload(self, *args, **kwargs):
        return None


# Singleton
_db: Optional[LocalDatabase] = None


def get_local_db() -> LocalDatabase:
    global _db
    if _db is None:
        _db = LocalDatabase()
    return _db


def get_local_supabase_client() -> LocalDatabase:
    """Drop-in replacement for create_client / get_supabase_client."""
    return get_local_db()
