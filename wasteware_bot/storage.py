from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .domain import TicketStatus, TelegramUser


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    banned INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    mode TEXT NOT NULL,
                    step TEXT,
                    data TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    data TEXT NOT NULL,
                    admin_note TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ticket_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                    actor_id INTEGER,
                    event_type TEXT NOT NULL,
                    body TEXT,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);
                CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
                CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id);
                """
            )

    def upsert_user(self, user: TelegramUser, is_admin: bool = False) -> None:
        now = int(time.time())
        role = "admin" if is_admin else "user"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, username, first_name, last_name, language_code, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    language_code=excluded.language_code,
                    role=CASE WHEN users.role = 'admin' THEN 'admin' ELSE excluded.role END,
                    updated_at=excluded.updated_at
                """,
                (user.id, user.username, user.first_name, user.last_name, user.language_code, role, now, now),
            )

    def user_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users WHERE banned = 0").fetchone()[0])

    def users(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM users WHERE banned = 0 ORDER BY created_at DESC"))

    def user(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def set_session(self, user_id: int, mode: str, step: str | None, data: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (user_id, mode, step, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mode=excluded.mode,
                    step=excluded.step,
                    data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (user_id, mode, step, json.dumps(data, ensure_ascii=False), int(time.time())),
            )

    def get_session(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {"mode": row["mode"], "step": row["step"], "data": json.loads(row["data"] or "{}")}

    def clear_session(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def create_ticket(self, user_id: int, data: dict[str, Any]) -> int:
        now = int(time.time())
        body = json.dumps(data, ensure_ascii=False)
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO tickets (user_id, status, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, TicketStatus.NEW.value, body, now, now),
            )
            ticket_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO ticket_events (ticket_id, actor_id, event_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, user_id, "created", body, now),
            )
            return ticket_id

    def ticket(self, ticket_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

    def user_tickets(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                )
            )

    def tickets_by_status(self, statuses: list[TicketStatus], limit: int = 20) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in statuses)
        values = [status.value for status in statuses]
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"SELECT * FROM tickets WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?",
                    (*values, limit),
                )
            )

    def set_ticket_status(self, ticket_id: int, status: TicketStatus, actor_id: int, note: str | None = None) -> bool:
        now = int(time.time())
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE tickets SET status = ?, admin_note = COALESCE(?, admin_note), updated_at = ? WHERE id = ?",
                (status.value, note, now, ticket_id),
            )
            if cur.rowcount == 0:
                return False
            conn.execute(
                "INSERT INTO ticket_events (ticket_id, actor_id, event_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, actor_id, "status", status.value if note is None else f"{status.value}: {note}", now),
            )
            return True

    def add_ticket_message(self, ticket_id: int, actor_id: int, body: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO ticket_events (ticket_id, actor_id, event_type, body, created_at) VALUES (?, ?, 'message', ?, ?)",
                (ticket_id, actor_id, body, int(time.time())),
            )

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS c FROM tickets GROUP BY status").fetchall()
            users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        result = {status.value: 0 for status in TicketStatus}
        result.update({row["status"]: int(row["c"]) for row in rows})
        result["users"] = int(users)
        return result

    def record_broadcast(self, admin_id: int, body: str, delivered: int, failed: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO broadcasts (admin_id, body, delivered, failed, created_at) VALUES (?, ?, ?, ?, ?)",
                (admin_id, body, delivered, failed, int(time.time())),
            )
            return int(cur.lastrowid)

