"""One durable active reviewer lease across tabs; disconnected gaps are excluded."""

import math
import time

from workflows.review_store import ReviewConflict


class ReviewTiming:
    def __init__(self, store):
        self.store = store

    def _stop(self, db, timer, until, reason):
        if timer["review"] is None:
            return
        seconds = max(0, until - timer["started"])
        db.execute("INSERT INTO review_time(review,seconds) VALUES(?,?) ON CONFLICT(review) DO UPDATE SET seconds=seconds+excluded.seconds", (timer["review"], seconds))
        db.execute("UPDATE timer SET review=NULL,tab=NULL,started=NULL,heartbeat=NULL WHERE singleton=1")
        self.store.event(db, "review_timer_stopped", request=timer["review"], seconds=seconds, reason=reason)

    def update(self, *, request, tab, action, seconds=None, reason=None):
        if not isinstance(tab, str) or not 8 <= len(tab) <= 128:
            raise ValueError("browser tab identity required")
        if action not in ("start", "heartbeat", "pause", "adjust", "status"):
            raise ValueError("invalid timer action")
        with self.store.transaction() as db:
            review = db.execute("SELECT state FROM reviews WHERE id=?", (request,)).fetchone()
            if review is None:
                raise ReviewConflict("review unavailable")
            now = time.time()
            timer = db.execute("SELECT * FROM timer WHERE singleton=1").fetchone()
            if timer["review"] and (now-timer["heartbeat"] > 3 or now < timer["heartbeat"]):
                self._stop(db, timer, timer["heartbeat"], "connection_lost_or_clock_changed")
                timer = db.execute("SELECT * FROM timer WHERE singleton=1").fetchone()
            owner = timer["review"] == request and timer["tab"] == tab
            if action == "start":
                if review["state"] != "pending":
                    raise ReviewConflict("only a ready review can start its timer")
                if timer["review"] is not None and not owner:
                    raise ReviewConflict("another tab or review has the active timer")
                if timer["review"] is None:
                    db.execute("UPDATE timer SET review=?,tab=?,started=?,heartbeat=? WHERE singleton=1", (request,tab,now,now))
                    self.store.event(db, "review_timer_started", request=request, tab=tab)
            elif action == "heartbeat" and owner:
                if review["state"] != "pending":
                    self._stop(db, timer, now, "review_answered")
                else:
                    db.execute("UPDATE timer SET heartbeat=? WHERE singleton=1", (now,))
            elif action == "pause" and owner:
                self._stop(db, timer, now, "explicit_or_hidden")
            elif action == "adjust":
                if not isinstance(seconds, (int,float)) or not math.isfinite(seconds) or abs(seconds)>86400 or not isinstance(reason,str) or not reason.strip() or len(reason)>2048:
                    raise ValueError("bounded manual adjustment and explanation required")
                was_active = timer["review"] == request
                if was_active:
                    self._stop(db,timer,now,"manual_adjustment")
                db.execute("INSERT OR IGNORE INTO review_time(review,seconds) VALUES(?,0)", (request,))
                db.execute("UPDATE review_time SET seconds=MAX(0,seconds+?) WHERE review=?", (seconds,request))
                if was_active:
                    db.execute("UPDATE timer SET review=?,tab=?,started=?,heartbeat=? WHERE singleton=1", (request,timer["tab"],now,now))
                self.store.event(db, "review_timer_adjusted", request=request, seconds=seconds, reason=reason)
            timer = db.execute("SELECT * FROM timer WHERE singleton=1").fetchone()
            saved = db.execute("SELECT seconds FROM review_time WHERE review=?", (request,)).fetchone()
            total = saved[0] if saved else 0
            if timer["review"] == request:
                total += max(0, now-timer["started"])
            return {"seconds": total, "running": timer["review"] == request, "this_tab": timer["review"] == request and timer["tab"] == tab}
