"""Private evaluation reference. Never copy this into model task checkouts."""

import copy
import json
import sqlite3


def integer(value, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError("integer required")
    return value


def identifier(value):
    if not isinstance(value, str) or not value:
        raise ValueError("nonempty identifier required")
    return value


def normalize(job):
    allowed = {"id", "payload", "priority", "dependencies", "max_attempts", "ready_at"}
    if not isinstance(job, dict) or set(job) - allowed or "id" not in job:
        raise ValueError("invalid job")
    result = dict(
        id=identifier(job["id"]),
        payload=job.get("payload", {}),
        priority=integer(job.get("priority", 0)),
        dependencies=job.get("dependencies", []),
        max_attempts=integer(job.get("max_attempts", 3), 1),
        ready_at=integer(job.get("ready_at", 0), 0),
    )
    if result["max_attempts"] > 100 or not isinstance(result["payload"], dict):
        raise ValueError("invalid attempts/payload")
    if not isinstance(result["dependencies"], list):
        raise ValueError("invalid dependencies")
    result["dependencies"] = sorted({identifier(dep) for dep in result["dependencies"]})
    try:
        return json.loads(json.dumps(result, allow_nan=False))
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid JSON payload") from None


class Queue:
    def __init__(self, db_path):
        self.db_path = db_path
        connection = sqlite3.connect(db_path, timeout=5)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS reference_jobs (id TEXT PRIMARY KEY, original TEXT NOT NULL, current TEXT NOT NULL)"
            )
            connection.commit()
        finally:
            connection.close()

    def transaction(self, operation):
        connection = sqlite3.connect(self.db_path, timeout=5)
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = {
                key: (json.loads(original), json.loads(current))
                for key, original, current in connection.execute(
                    "SELECT * FROM reference_jobs"
                )
            }
            result = operation(rows)
            connection.execute("DELETE FROM reference_jobs")
            connection.executemany(
                "INSERT INTO reference_jobs VALUES (?, ?, ?)",
                [
                    (key, json.dumps(original), json.dumps(current))
                    for key, (original, current) in rows.items()
                ],
            )
            connection.commit()
            return copy.deepcopy(result)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def submit(self, jobs):
        if not isinstance(jobs, list):
            raise ValueError("batch must be a list")
        normalized = [normalize(job) for job in jobs]
        if len({job["id"] for job in normalized}) != len(normalized):
            raise ValueError("duplicate batch ID")

        def action(rows):
            for original in normalized:
                key = original["id"]
                if key in rows:
                    if json.dumps(rows[key][0], sort_keys=True) != json.dumps(
                        original, sort_keys=True
                    ):
                        raise ValueError("conflicting job")
                else:
                    current = dict(
                        original,
                        state="pending",
                        attempts=0,
                        worker=None,
                        lease_until=None,
                    )
                    rows[key] = (original, current)
            visiting, visited = set(), set()

            def visit(key):
                if key not in rows or key in visiting:
                    raise ValueError("unknown dependency or cycle")
                if key in visited:
                    return
                visiting.add(key)
                for dep in rows[key][0]["dependencies"]:
                    visit(dep)
                visiting.remove(key)
                visited.add(key)

            for key in rows:
                visit(key)
            return [rows[job["id"]][1] for job in normalized]

        return self.transaction(action)

    def get(self, id):
        identifier(id)
        return self.transaction(lambda rows: rows[id][1] if id in rows else None)

    def list(self):
        return self.transaction(lambda rows: [rows[key][1] for key in sorted(rows)])

    @staticmethod
    def recover_rows(rows, now):
        expired = []
        for key, (_, view) in sorted(rows.items()):
            if view["state"] == "running" and view["lease_until"] <= now:
                expired.append(key)
                if view["attempts"] < view["max_attempts"]:
                    view["state"] = "pending"
                    view["ready_at"] = view["lease_until"]
                else:
                    view["state"] = "failed"
                view["worker"] = view["lease_until"] = None
        return expired

    def recover(self, now):
        integer(now, 0)
        return self.transaction(lambda rows: self.recover_rows(rows, now))

    def claim(self, worker, now, lease_seconds):
        identifier(worker)
        integer(now, 0)
        integer(lease_seconds, 1)

        def action(rows):
            self.recover_rows(rows, now)
            eligible = [
                view
                for _, view in rows.values()
                if view["state"] == "pending"
                and view["ready_at"] <= now
                and view["attempts"] < view["max_attempts"]
                and all(
                    rows[dep][1]["state"] == "succeeded" for dep in view["dependencies"]
                )
            ]
            if not eligible:
                return None
            view = min(eligible, key=lambda item: (-item["priority"], item["id"]))
            view.update(
                state="running",
                attempts=view["attempts"] + 1,
                worker=worker,
                lease_until=now + lease_seconds,
            )
            return view

        return self.transaction(action)

    def finish(self, id, worker, attempt, now, outcome, delay):
        identifier(id)
        identifier(worker)
        integer(attempt, 1)
        integer(now, 0)
        integer(delay, 0)

        def action(rows):
            if id not in rows:
                raise ValueError("unknown job")
            view = rows[id][1]
            if (
                view["state"] != "running"
                or view["worker"] != worker
                or view["attempts"] != attempt
                or now >= view["lease_until"]
            ):
                raise ValueError("stale lease")
            if outcome == "succeeded":
                view["state"] = "succeeded"
            elif view["attempts"] < view["max_attempts"]:
                view.update(state="pending", ready_at=now + delay)
            else:
                view["state"] = "failed"
            view["worker"] = view["lease_until"] = None
            return view

        return self.transaction(action)

    def complete(self, id, worker, attempt, now):
        return self.finish(id, worker, attempt, now, "succeeded", 0)

    def fail(self, id, worker, attempt, now, retry_delay=0):
        return self.finish(id, worker, attempt, now, "failed", retry_delay)
