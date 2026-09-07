"""Initial durable storage; scheduling and lease behavior are unfinished."""

import json

from .storage import connect


class Queue:
    def __init__(self, db_path):
        self.db_path = db_path
        with connect(db_path):
            pass

    def submit(self, jobs):
        views = []
        with connect(self.db_path) as connection:
            for job in jobs:
                view = dict(
                    id=job["id"],
                    payload=job.get("payload", {}),
                    priority=job.get("priority", 0),
                    dependencies=job.get("dependencies", []),
                    max_attempts=job.get("max_attempts", 3),
                    ready_at=job.get("ready_at", 0),
                    state="pending",
                    attempts=0,
                    worker=None,
                    lease_until=None,
                )
                connection.execute(
                    "INSERT OR REPLACE INTO jobs VALUES (?, ?)",
                    (view["id"], json.dumps(view)),
                )
                views.append(view)
        return views

    def get(self, id):
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT data FROM jobs WHERE id=?", (id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with connect(self.db_path) as connection:
            return [
                json.loads(row[0])
                for row in connection.execute("SELECT data FROM jobs ORDER BY id")
            ]

    def claim(self, worker, now, lease_seconds):
        raise NotImplementedError("claim scheduling and atomic ownership")

    def recover(self, now):
        raise NotImplementedError("expired lease recovery")

    def complete(self, id, worker, attempt, now):
        raise NotImplementedError("completion validation")

    def fail(self, id, worker, attempt, now, retry_delay=0):
        raise NotImplementedError("retry state transition")
