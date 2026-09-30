import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


class EventDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._connect() as connection:
            columns = connection.execute("PRAGMA table_info(events)").fetchall()
            sensor_column = next((column for column in columns if column["name"] == "sensor_value"), None)
            if sensor_column is not None and sensor_column["notnull"]:
                connection.execute("ALTER TABLE events RENAME TO events_legacy")
                connection.execute(
                    """CREATE TABLE events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        sensor_value INTEGER CHECK(sensor_value IS NULL OR sensor_value BETWEEN 0 AND 1023),
                        status TEXT NOT NULL CHECK(status IN ('NORMAL', 'LEAKING')),
                        threshold INTEGER NOT NULL CHECK(threshold BETWEEN 0 AND 1023)
                    )"""
                )
                connection.execute(
                    """INSERT INTO events(id, timestamp, sensor_value, status, threshold)
                       SELECT id, timestamp, sensor_value, status, threshold FROM events_legacy"""
                )
                connection.execute("DROP TABLE events_legacy")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    sensor_value INTEGER CHECK(sensor_value IS NULL OR sensor_value BETWEEN 0 AND 1023),
                    status TEXT NOT NULL CHECK(status IN ('NORMAL', 'LEAKING')),
                    threshold INTEGER NOT NULL CHECK(threshold BETWEEN 0 AND 1023)
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)")

    def record_transition(self, timestamp: datetime, value: int | None, status: str, threshold: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO events(timestamp, sensor_value, status, threshold) VALUES (?, ?, ?, ?)",
                (timestamp.astimezone().isoformat(timespec="seconds"), value, status, threshold),
            )

    def recent_events(self, limit: int = 1000):
        with self._connect() as connection:
            return connection.execute(
                "SELECT id, timestamp, sensor_value, status, threshold FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def export_csv(self, destination: Path) -> int:
        count = 0
        with destination.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(("ID", "Timestamp", "Sensor", "Status", "Threshold"))
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT id, timestamp, sensor_value, status, threshold FROM events ORDER BY id"
                )
                for row in rows:
                    writer.writerow((row["id"], row["timestamp"], row["sensor_value"], row["status"], row["threshold"]))
                    count += 1
        return count

    def count_leakage_events(self) -> int:
        with self._connect() as connection:
            result = connection.execute("SELECT COUNT(*) FROM events WHERE status = 'LEAKING'").fetchone()
        return int(result[0])
