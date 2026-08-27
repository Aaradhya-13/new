import sqlite3
import time
from typing import List, Dict, Any

class HubSyncStore:
    def __init__(self, db_path: str = "hub_node.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS distress_sync (
                    cell_id TEXT,
                    category INTEGER,
                    headcount INTEGER,
                    severity INTEGER,
                    lat REAL,
                    lon REAL,
                    landmark TEXT,
                    first_seen REAL,
                    last_updated REAL,
                    status TEXT,
                    synced INTEGER DEFAULT 0,
                    PRIMARY KEY (cell_id, category)
                )
            """)

    def upsert_cluster(self, cluster: Dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO distress_sync 
                (cell_id, category, headcount, severity, lat, lon, landmark, first_seen, last_updated, status, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', 0)
                ON CONFLICT(cell_id, category) DO UPDATE SET
                    headcount = MAX(headcount, excluded.headcount),
                    last_updated = excluded.last_updated,
                    synced = 0
            """, (
                cluster["cell_id"], cluster["category"], cluster["headcount"],
                cluster["severity"], cluster["lat"], cluster["lon"],
                cluster["landmark"], cluster["first_seen"], cluster["last_updated"]
            ))

    def get_delta_payload(self, last_sync_timestamp: float) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM distress_sync WHERE last_updated > ?", (last_sync_timestamp,))
            return [dict(row) for row in cursor.fetchall()]

    def merge_carrier_delta(self, delta_records: List[Dict[str, Any]]):
        with sqlite3.connect(self.db_path) as conn:
            for rec in delta_records:
                conn.execute("""
                    INSERT INTO distress_sync 
                    (cell_id, category, headcount, severity, lat, lon, landmark, first_seen, last_updated, status, synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(cell_id, category) DO UPDATE SET
                        headcount = MAX(headcount, excluded.headcount),
                        last_updated = MAX(last_updated, excluded.last_updated)
                """, (
                    rec["cell_id"], rec["category"], rec["headcount"],
                    rec["severity"], rec["lat"], rec["lon"],
                    rec["landmark"], rec["first_seen"], rec["last_updated"], rec.get("status", "QUEUED")
                ))
