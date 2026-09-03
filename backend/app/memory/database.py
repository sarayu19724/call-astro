import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from app.config.settings import settings
from app.utils.logger import logger

class MemoryDatabase:
    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        logger.info(f"Initialising database at {self.db_path}")
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    dob TEXT,
                    birth_time TEXT,
                    birth_place TEXT,
                    gender TEXT,
                    name TEXT,
                    language TEXT DEFAULT 'Hinglish',
                    pending_field TEXT,
                    kundli_data TEXT,
                    kundli_raw TEXT,
                    kundli_dasha TEXT,
                    kundli_divisional TEXT,
                    kundli_full_raw TEXT,
                    topic_memory TEXT,
                    last_reasoning_trace TEXT,
                    dashboard_prediction TEXT,
                    dashboard_lucky_color TEXT,
                    dashboard_date TEXT,
                    weekly_guidance TEXT,
                    weekly_week_start TEXT,
                    yoga_text TEXT,
                    dasha_tree_raw TEXT,
                    topic_cache TEXT,
                    house_insights_cache TEXT,
                    kundli_fetch_status TEXT,
                    kundli_fetch_error TEXT,
                    kundli_fetch_started_at TEXT,
                    latitude REAL,
                    longitude REAL,
                    updated_at TEXT
                )
            """)

            cursor.execute("PRAGMA table_info(sessions)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col_name, col_type in [
                ("latitude", "REAL"),
                ("longitude", "REAL"),
                ("pending_field", "TEXT"),
                ("kundli_data", "TEXT"),
                ("kundli_raw", "TEXT"),
                ("kundli_dasha", "TEXT"),
                ("kundli_divisional", "TEXT"),
                ("kundli_full_raw", "TEXT"),
                ("topic_memory", "TEXT"),
                ("last_reasoning_trace", "TEXT"),
                ("dashboard_prediction", "TEXT"),
                ("dashboard_lucky_color", "TEXT"),
                ("dashboard_date", "TEXT"),
                ("weekly_guidance", "TEXT"),
                ("weekly_week_start", "TEXT"),
                ("yoga_text", "TEXT"),
                ("dasha_tree_raw", "TEXT"),
                ("topic_cache", "TEXT"),
                ("house_insights_cache", "TEXT"),
                ("kundli_fetch_status", "TEXT"),
                ("kundli_fetch_error", "TEXT"),
                ("kundli_fetch_started_at", "TEXT"),
            ]:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Migrated sessions table: added {col_name} column")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def get_or_create_session(self, session_id: str) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            now_str = datetime.utcnow().isoformat()
            cursor.execute(
                """
                INSERT INTO sessions (session_id, dob, birth_time, birth_place, language,
                                       pending_field, kundli_data, kundli_raw, kundli_dasha, kundli_divisional,
                                       kundli_full_raw, topic_memory, last_reasoning_trace, dashboard_prediction,
                                       dashboard_lucky_color, dashboard_date, yoga_text, dasha_tree_raw, topic_cache,
                                       house_insights_cache,
                                       kundli_fetch_status, kundli_fetch_error, kundli_fetch_started_at,
                                       latitude, longitude, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, None, None, None, 'Hinglish', None, None, None, None, None,
                 None, None, None, None, None, None, None, None, None, None,
                 "idle", None, None, None, None, now_str)
            )
            conn.commit()

            return {
                "session_id": session_id, "dob": None, "birth_time": None, "birth_place": None,
                "gender": None, "name": None, "language": "Hinglish", "pending_field": None,
                "kundli_data": None, "kundli_raw": None, "kundli_dasha": None, "kundli_divisional": None,
                "kundli_full_raw": None,
                "topic_memory": None, "last_reasoning_trace": None,
                "dashboard_prediction": None, "dashboard_lucky_color": None, "dashboard_date": None,
                "yoga_text": None, "dasha_tree_raw": None, "topic_cache": None,
                "house_insights_cache": None,
                "kundli_fetch_status": "idle", "kundli_fetch_error": None, "kundli_fetch_started_at": None,
                "latitude": None, "longitude": None, "updated_at": now_str
            }

    def update_session(self, session_id: str, updates: Dict) -> Dict:
        if not updates:
            return self.get_or_create_session(session_id)

        allowed_fields = {
            "dob", "birth_time", "birth_place", "gender", "name", "language",
            "latitude", "longitude", "pending_field", "kundli_data", "kundli_raw", "kundli_dasha",
            "kundli_divisional", "kundli_full_raw", "topic_memory", "last_reasoning_trace",
            "dashboard_prediction", "dashboard_lucky_color", "dashboard_date",
            "weekly_guidance", "weekly_week_start", "yoga_text", "dasha_tree_raw", "topic_cache",
            "house_insights_cache",
            "kundli_fetch_status", "kundli_fetch_error", "kundli_fetch_started_at"
        }
        nullable_ok = {
            "pending_field", "kundli_data", "kundli_raw", "kundli_dasha", "kundli_divisional",
            "kundli_full_raw", "topic_memory", "last_reasoning_trace",
            "dashboard_prediction", "dashboard_lucky_color", "dashboard_date",
            "weekly_guidance", "weekly_week_start", "yoga_text", "dasha_tree_raw", "topic_cache",
            "house_insights_cache",
            "kundli_fetch_status", "kundli_fetch_error", "kundli_fetch_started_at"
        }
        fields_to_update = {
            k: v for k, v in updates.items()
            if k in allowed_fields and (v is not None or k in nullable_ok)
        }

        if not fields_to_update:
            return self.get_or_create_session(session_id)

        fields_to_update["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join([f"{k} = ?" for k in fields_to_update.keys()])
        params = list(fields_to_update.values()) + [session_id]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE sessions SET {set_clause} WHERE session_id = ?", params)
            conn.commit()

        return self.get_or_create_session(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> Dict:
        self.get_or_create_session(session_id)
        now_str = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now_str)
            )
            conn.commit()
        return {"session_id": session_id, "role": role, "content": content, "timestamp": now_str}

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows][-limit:]

    def clear_history(self, session_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute("UPDATE sessions SET topic_memory = NULL, updated_at = ? WHERE session_id = ?",
                           (datetime.utcnow().isoformat(), session_id))
            conn.commit()

db = MemoryDatabase()