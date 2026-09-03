import sqlite3
import os
from datetime import datetime
from typing import Dict
from app.config.settings import settings

COUPLE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(settings.DATABASE_PATH)), "couple_sessions.db")


class CoupleDatabase:
    def __init__(self, db_path: str = COUPLE_DB_PATH):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS couple_sessions (
                    couple_id TEXT PRIMARY KEY,
                    language TEXT DEFAULT 'Hinglish',
                    partner1_name TEXT, partner1_dob TEXT, partner1_time TEXT, partner1_place TEXT,
                    partner1_status TEXT DEFAULT 'idle', partner1_error TEXT, partner1_data TEXT,
                    partner2_name TEXT, partner2_dob TEXT, partner2_time TEXT, partner2_place TEXT,
                    partner2_status TEXT DEFAULT 'idle', partner2_error TEXT, partner2_data TEXT,
                    childbirth_analysis TEXT,
                    known_outcome TEXT,
                    chat_history TEXT,
                    updated_at TEXT
                )
            """)

            cursor.execute("PRAGMA table_info(couple_sessions)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "known_outcome" not in existing_cols:
                cursor.execute("ALTER TABLE couple_sessions ADD COLUMN known_outcome TEXT")

            conn.commit()

    def get_or_create(self, couple_id: str) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM couple_sessions WHERE couple_id = ?", (couple_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO couple_sessions (couple_id, updated_at) VALUES (?, ?)",
                (couple_id, now)
            )
            conn.commit()
            cursor.execute("SELECT * FROM couple_sessions WHERE couple_id = ?", (couple_id,))
            return dict(cursor.fetchone())

    def update(self, couple_id: str, updates: Dict) -> Dict:
        self.get_or_create(couple_id)
        allowed = {
            "language",
            "partner1_name", "partner1_dob", "partner1_time", "partner1_place",
            "partner1_status", "partner1_error", "partner1_data",
            "partner2_name", "partner2_dob", "partner2_time", "partner2_place",
            "partner2_status", "partner2_error", "partner2_data",
            "childbirth_analysis", "known_outcome", "chat_history",
        }
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return self.get_or_create(couple_id)
        fields["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        params = list(fields.values()) + [couple_id]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE couple_sessions SET {set_clause} WHERE couple_id = ?", params)
            conn.commit()
        return self.get_or_create(couple_id)

    def delete(self, couple_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM couple_sessions WHERE couple_id = ?", (couple_id,))
            conn.commit()


couple_db = CoupleDatabase()