"""Durable single-reviewer broker. Every mutation commits before its receipt."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

from workflows.review_projection import validate_presentation
from workflows.review_ownership import ownership_alive


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class ReviewConflict(ValueError):
    pass


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trials (
                    id TEXT PRIMARY KEY, block_id TEXT NOT NULL, scenario TEXT NOT NULL,
                    generation TEXT NOT NULL, identity TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                    submissions INTEGER NOT NULL DEFAULT 0, question_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, trial TEXT NOT NULL REFERENCES trials(id),
                    revision INTEGER NOT NULL, generation TEXT NOT NULL, kind TEXT NOT NULL,
                    state TEXT NOT NULL, raw TEXT NOT NULL, presented TEXT NOT NULL,
                    raw_hash TEXT NOT NULL, presented_hash TEXT NOT NULL,
                    created REAL NOT NULL, ready REAL, continued REAL, unread INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS answers (
                    request TEXT PRIMARY KEY REFERENCES reviews(id), key TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL, receipt TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS timer (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), review TEXT,
                    tab TEXT, started REAL, heartbeat REAL);
                INSERT OR IGNORE INTO timer(singleton) VALUES(1);
                CREATE TABLE IF NOT EXISTS review_time (
                    review TEXT PRIMARY KEY, seconds REAL NOT NULL DEFAULT 0);
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, kind, **payload):
        db.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)",
                   (time.time(), kind, encoded(payload)))

    def register(self, *, trial, block, scenario, generation, identity, title):
        if not ownership_alive(identity):
            raise ReviewConflict("runner and runtime ownership required")
        if not all(isinstance(x, str) and 0 < len(x) <= 256
                   for x in (trial, block, scenario, generation, title)):
            raise ValueError("bounded trial identity required")
        with self.transaction() as db:
            old = db.execute("SELECT * FROM trials WHERE id=?", (trial,)).fetchone()
            if old:
                if (old["block_id"], old["scenario"], old["generation"], old["identity"], old["title"]) != (block, scenario, generation, encoded(identity), title):
                    raise ReviewConflict("conflicting trial registration")
                return old["code"]
            active = db.execute("SELECT * FROM trials WHERE state='live'").fetchall()
            if len(active) >= 2 or any(row["scenario"] == scenario for row in active):
                raise ReviewConflict("live slot or scenario already occupied")
            code = secrets.token_hex(4).upper()
            db.execute("INSERT INTO trials(id,block_id,scenario,generation,identity,code,title,state,created) VALUES(?,?,?,?,?,?,?,'live',?)",
                       (trial, block, scenario, generation, encoded(identity), code, title, time.time()))
            self.event(db, "trial_registered", trial=trial, generation=generation)
            return code

    def publish(self, *, trial, generation, revision, kind, raw, presented, checkpoint_id=None):
        if kind not in ("clarification", "plan", "product") or type(revision) is not int or revision < 1:
            raise ValueError("invalid checkpoint")
        if len(encoded(raw).encode()) > 65536 or len(encoded(presented).encode()) > 65536:
            raise ValueError("checkpoint exceeds limit")
        validate_presentation(presented)
        request = checkpoint_id or uuid.uuid5(uuid.NAMESPACE_OID, encoded([trial, generation, revision, kind])).hex
        if not isinstance(request, str) or len(request) != 32 or any(c not in "0123456789abcdef" for c in request):
            raise ValueError("opaque checkpoint UUID required")
        with self.transaction() as db:
            self._trial(db, trial, generation)
            old = db.execute("SELECT * FROM reviews WHERE id=?", (request,)).fetchone()
            if old:
                if (old["trial"], old["generation"], old["revision"], old["kind"], old["raw_hash"], old["presented_hash"]) != (trial, generation, revision, kind, digest(raw), digest(presented)):
                    raise ReviewConflict("conflicting repeated checkpoint publication")
                return request
            pending = db.execute("SELECT 1 FROM reviews WHERE trial=? AND state IN ('created','pausing','pending','answered','consumed') AND continued IS NULL", (trial,)).fetchone()
            if pending:
                raise ReviewConflict("trial already has an unresolved checkpoint")
            db.execute("INSERT INTO reviews(id,trial,revision,generation,kind,state,raw,presented,raw_hash,presented_hash,created) VALUES(?,?,?,?,?,'created',?,?,?,?,?)",
                       (request, trial, revision, generation, kind, encoded(raw), encoded(presented), digest(raw), digest(presented), time.time()))
            self.event(db, "review_created", request=request)
            return request

    def _trial(self, db, trial, generation):
        row = db.execute("SELECT * FROM trials WHERE id=?", (trial,)).fetchone()
        if row is None or row["generation"] != generation or row["state"] != "live":
            raise ReviewConflict("execution generation unavailable")
        if not ownership_alive(json.loads(row["identity"])):
            raise ReviewConflict("runtime ownership unavailable")
        return row

    def _request(self, db, request, trial, generation, revision):
        self._trial(db, trial, generation)
        row = db.execute("SELECT * FROM reviews WHERE id=?", (request,)).fetchone()
        if row is None or (row["trial"], row["generation"], row["revision"]) != (trial, generation, revision):
            raise ReviewConflict("checkpoint identity mismatch")
        return row

    def transition(self, *, request, trial, generation, revision, state, evidence=None):
        expected = {"pausing": "created", "pending": "pausing"}
        if state not in expected:
            raise ValueError("invalid checkpoint transition")
        with self.transaction() as db:
            row = self._request(db, request, trial, generation, revision)
            if row["state"] == state:
                return
            if row["state"] != expected[state]:
                raise ReviewConflict("checkpoint transition conflict")
            if state == "pending" and (not isinstance(evidence, dict) or evidence.get("quiescent") is not True):
                raise ValueError("verified pause evidence required")
            db.execute("UPDATE reviews SET state=?,ready=? WHERE id=?",
                       (state, time.time() if state == "pending" else None, request))
            self.event(db, "review_" + state, request=request, evidence=evidence)

    def _expire(self, db):
        now = time.time()
        rows = db.execute("SELECT r.id,r.trial FROM reviews r JOIN trials t ON r.trial=t.id WHERE t.state='live' AND ((r.state='pending' AND r.ready<=?) OR t.created<=?)", (now-86400, now-7*86400)).fetchall()
        for row in rows:
            db.execute("UPDATE reviews SET state='expired' WHERE id=?", (row["id"],))
            db.execute("UPDATE trials SET state='expired' WHERE id=?", (row["trial"],))
            self.event(db, "review_expired", request=row["id"])

    def list_reviews(self):
        with self.transaction() as db:
            self._expire(db)
            rows = db.execute("SELECT r.id,r.kind,r.state,r.ready,r.unread,r.continued,t.code,t.title,a.created AS answered_at FROM reviews r JOIN trials t ON t.id=r.trial LEFT JOIN answers a ON a.request=r.id ORDER BY COALESCE(r.ready,r.created),r.id").fetchall()
            return [dict(row) for row in rows]

    def detail(self, request):
        with self.transaction() as db:
            self._expire(db)
            row = db.execute("SELECT r.id,r.kind,r.state,r.revision,r.presented,r.presented_hash,r.ready,r.continued,t.code,t.title FROM reviews r JOIN trials t ON t.id=r.trial WHERE r.id=?", (request,)).fetchone()
            if row is None:
                raise ReviewConflict("review unavailable")
            db.execute("UPDATE reviews SET unread=0 WHERE id=?", (request,))
            return dict(row) | {"presented": json.loads(row["presented"]) if row["state"] not in ("created", "pausing") else {}}

    def submit(self, request, *, key, revision, presented_hash, action, text="", answers=None, new_scope=False):
        if not isinstance(key, str) or not 8 <= len(key) <= 128 or not isinstance(text, str) or len(text.encode()) > 16384:
            raise ValueError("invalid response size or idempotency key")
        payload = dict(revision=revision, presented_hash=presented_hash, action=action, text=text, answers=answers, new_scope=new_scope)
        if len(encoded(payload).encode()) > 32768 or type(new_scope) is not bool:
            raise ValueError("invalid response")
        with self.transaction() as db:
            self._expire(db)
        with self.transaction() as db:
            old = db.execute("SELECT * FROM answers WHERE key=? OR request=?", (key, request)).fetchone()
            if old:
                if (old["key"], old["request"], old["payload"]) != (key, request, encoded(payload)):
                    raise ReviewConflict("conflicting repeated submission")
                return json.loads(old["receipt"])
            self._expire(db)
            row = db.execute("SELECT * FROM reviews WHERE id=?", (request,)).fetchone()
            if row is None or row["state"] != "pending" or row["revision"] != revision or row["presented_hash"] != presented_hash:
                raise ReviewConflict("review is stale or unavailable")
            trial = self._trial(db, row["trial"], row["generation"])
            actions = {"clarification": {"answer", "cannot_decide"}, "plan": {"approve", "request_changes", "cannot_decide"}, "product": {"accept", "request_changes", "cannot_judge"}}
            if action not in actions[row["kind"]] or (action == "request_changes" and not text.strip()):
                raise ValueError("invalid action or missing explanation")
            if row["kind"] != "product" and trial["submissions"] >= 20:
                raise ReviewConflict("human submission allowance exhausted")
            questions = json.loads(row["presented"]).get("questions", [])
            if action == "answer":
                ids = {q["id"] for q in questions}
                if not isinstance(answers, dict) or set(answers) != ids or any(not isinstance(v, list) or not v or any(not isinstance(s, str) or not s.strip() for s in v) for v in answers.values()):
                    raise ValueError("exact question answers required")
            receipt = {"id": uuid.uuid4().hex, "request": request, "status": "answer_saved"}
            db.execute("INSERT INTO answers VALUES(?,?,?,?,?)", (request, key, encoded(payload), encoded(receipt), time.time()))
            db.execute("UPDATE reviews SET state='answered' WHERE id=?", (request,))
            from workflows.review_timing import ReviewTiming
            timer = db.execute("SELECT * FROM timer WHERE singleton=1").fetchone()
            if timer["review"] == request:
                now = time.time()
                until = now if now-timer["heartbeat"] <= 3 else timer["heartbeat"]
                ReviewTiming(self)._stop(db, timer, until, "answer_committed")
            db.execute("UPDATE trials SET submissions=submissions+1,question_count=question_count+? WHERE id=?", (len(questions), row["trial"]))
            self.event(db, "answer_committed", request=request, receipt=receipt["id"])
            return receipt

    def consume(self, *, request, trial, generation, revision):
        with self.transaction() as db:
            row = self._request(db, request, trial, generation, revision)
            if row["state"] != "answered":
                raise ReviewConflict("answer not available for consumption")
            answer = db.execute("SELECT payload FROM answers WHERE request=?", (request,)).fetchone()
            db.execute("UPDATE reviews SET state='consumed' WHERE id=?", (request,))
            self.event(db, "answer_consumed", request=request)
            return json.loads(answer["payload"])

    def status(self, *, request, trial, generation, revision):
        with self.transaction() as db:
            self._expire(db)
            row = db.execute("SELECT * FROM reviews WHERE id=?",(request,)).fetchone()
            if row is None or (row['trial'],row['generation'],row['revision']) != (trial,generation,revision):
                raise ReviewConflict('checkpoint identity mismatch')
            answer = db.execute("SELECT created FROM answers WHERE request=?", (request,)).fetchone()
            return {"state": row["state"], "continued": row["continued"], "answered_at": answer[0] if answer else None}

    def continued(self, *, request, trial, generation, revision, evidence):
        with self.transaction() as db:
            row = self._request(db, request, trial, generation, revision)
            if row["state"] != "consumed" or not evidence:
                raise ReviewConflict("continuation acknowledgement conflict")
            if row["continued"] is not None:
                return
            db.execute("UPDATE reviews SET continued=? WHERE id=?", (time.time(), request))
            self.event(db, "continuation_observed", request=request, evidence=evidence)

    def interrupt(self, trial, generation, reason, status="interrupted"):
        if status not in ('interrupted','pause_failed') or not isinstance(reason,str) or len(reason)>2048:
            raise ValueError('invalid interruption record')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM trials WHERE id=?',(trial,)).fetchone()
            if row is None or row['generation']!=generation or row['state'] not in ('live',status):
                raise ReviewConflict('execution generation unavailable')
            if row['state']==status: return
            db.execute("UPDATE trials SET state=? WHERE id=?", (status,trial))
            db.execute("UPDATE reviews SET state=? WHERE trial=? AND continued IS NULL AND state IN ('created','pausing','pending','answered','consumed')", (status,trial))
            self.event(db, "trial_"+status, trial=trial, reason=reason)

    def withdraw(self, request, *, reason=""):
        if not isinstance(reason,str) or len(reason.encode())>2048:
            raise ValueError("bounded withdrawal reason required")
        with self.transaction() as db:
            row=db.execute("SELECT * FROM reviews WHERE id=?",(request,)).fetchone()
            if row is None or row['state'] not in ('created','pausing','pending','answered'):
                raise ReviewConflict("review cannot be withdrawn")
            db.execute("UPDATE reviews SET state='withdrawn' WHERE id=?",(request,))
            db.execute("UPDATE trials SET state='withdrawn' WHERE id=?",(row['trial'],))
            from workflows.review_timing import ReviewTiming
            timer=db.execute("SELECT * FROM timer WHERE singleton=1").fetchone()
            if timer['review']==request:
                ReviewTiming(self)._stop(db,timer,min(time.time(),timer['heartbeat']+3),'withdrawn')
            self.event(db,'review_withdrawn',request=request,reason=reason)
            return {'status':'withdrawn'}

    def reconcile_ownership(self):
        with self.transaction() as db:
            self._expire(db)
            rows = db.execute("SELECT * FROM trials WHERE state='live'").fetchall()
            for row in rows:
                identity = json.loads(row["identity"])
                if not ownership_alive(identity):
                    db.execute("UPDATE trials SET state='interrupted' WHERE id=?", (row["id"],))
                    db.execute("UPDATE reviews SET state='interrupted' WHERE trial=? AND continued IS NULL", (row["id"],))
                    self.event(db, "runtime_ownership_lost", trial=row["id"])
