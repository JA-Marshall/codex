"""Loopback-only review HTTP surfaces, with separate reviewer/runner credentials."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

from workflows.review_store import ReviewStore, ReviewConflict
from workflows.review_timing import ReviewTiming


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, store, *, port=0, reviewer_token=None, runner_token=None):
        self.store = store
        self.reviewer_token = reviewer_token or secrets.token_urlsafe(32)
        self.runner_token = runner_token or secrets.token_urlsafe(32)
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reviewer_sessions(id TEXT PRIMARY KEY,csrf TEXT NOT NULL,created REAL NOT NULL)")
        super().__init__(("127.0.0.1", port), ReviewHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"

    def service_actions(self):
        self.store.reconcile_ownership()

    def session(self, session_id):
        with self.store.transaction() as db:
            row=db.execute("SELECT csrf FROM reviewer_sessions WHERE id=? AND created>?",(session_id,time.time()-7*86400)).fetchone()
            return row[0] if row else None


class ReviewHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, *, content_type="application/json", cookie=None):
        body = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def auth(self, *, runner=False, mutation=False):
        server = self.server
        if self.headers.get("Host") != urlsplit(server.origin).netloc:
            raise PermissionError("invalid host")
        origin = self.headers.get("Origin")
        if origin is not None and origin != server.origin:
            raise PermissionError("cross-origin request")
        if self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
            raise PermissionError("cross-site request")
        if runner:
            token = self.headers.get("Authorization", "")
            if not secrets.compare_digest(token, "Bearer " + server.runner_token):
                raise PermissionError("runner authentication required")
            return
        cookies = dict(part.strip().split("=", 1) for part in self.headers.get("Cookie", "").split(";") if "=" in part)
        session = server.session(cookies.get("review_session"))
        if session is None:
            raise PermissionError("reviewer authentication required")
        if mutation and (origin != server.origin or not secrets.compare_digest(self.headers.get("X-Review-CSRF", ""), session)):
            raise PermissionError("CSRF check failed")
        return session

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 131072 or self.headers.get_content_type() != "application/json":
            raise ValueError("bounded JSON request required")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if path in static:
                if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
                    raise PermissionError("invalid host")
                file = Path(__file__).with_name("review_ui") / static[path]
                types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
                self.send(200, file.read_bytes(), content_type=types[file.suffix])
                return
            if path == "/api/session":
                self.send(200, {"csrf": self.auth()})
            elif path == "/api/reviews":
                self.auth()
                self.send(200, self.server.store.list_reviews())
            elif path.startswith("/api/reviews/") and len(path.split("/")) == 4:
                self.auth()
                self.send(200, self.server.store.detail(path.split("/")[3]))
            else:
                self.send(404, {"error": "Not found"})
        except PermissionError:
            self.send(403, {"error": "Open the reviewer entry link to connect."})
        except (ValueError, KeyError):
            self.send(400, {"error": "Review unavailable."})

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path == "/api/session":
                if self.headers.get("Origin") != self.server.origin or self.headers.get("Host") != urlsplit(self.server.origin).netloc:
                    raise PermissionError("invalid origin")
                body = self.body()
                if not secrets.compare_digest(str(body.get("token", "")), self.server.reviewer_token):
                    raise PermissionError("invalid entry token")
                session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with self.server.store.transaction() as db:
                    db.execute("DELETE FROM reviewer_sessions WHERE created<?",(time.time()-7*86400,))
                    db.execute("INSERT INTO reviewer_sessions VALUES(?,?,?)",(session,csrf,time.time()))
                self.send(200, {"csrf": csrf}, cookie=f"review_session={session}; HttpOnly; SameSite=Strict; Path=/")
                return
            if path.startswith("/runner/"):
                self.auth(runner=True, mutation=True)
                body = self.body()
                routes = {"register": self.server.store.register, "publish": self.server.store.publish,
                          "status": self.server.store.status,
                          "transition": self.server.store.transition, "consume": self.server.store.consume,
                          "continued": self.server.store.continued, "interrupt": self.server.store.interrupt}
                operation = path.removeprefix("/runner/")
                if operation not in routes:
                    raise ValueError("unsupported operation")
                self.send(200, {"result": routes[operation](**body)})
                return
            self.auth(mutation=True)
            if path == "/api/timer":
                self.send(200, ReviewTiming(self.server.store).update(**self.body()))
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[1:3] == ["api", "reviews"] and parts[4] == "response":
                self.send(200, self.server.store.submit(parts[3], **self.body()))
            elif len(parts) == 5 and parts[1:3] == ["api", "reviews"] and parts[4] == "withdraw":
                self.send(200,self.server.store.withdraw(parts[3],**self.body()))
            else:
                self.send(404, {"error": "Not found"})
        except PermissionError:
            self.send(403, {"error": "Authentication or origin check failed."})
        except ReviewConflict as error:
            self.send(409, {"error": str(error) if path == "/api/timer" else "Review changed or response conflicts. Refresh to check its saved state."})
        except (ValueError, TypeError, KeyError):
            self.send(400, {"error": "Invalid review request."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8878)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = args.directory / "credentials.json"
    if credentials.exists():
        tokens = json.loads(credentials.read_text())
    else:
        tokens = {"reviewer_token": secrets.token_urlsafe(32), "runner_token": secrets.token_urlsafe(32)}
        with credentials.open("x") as stream:
            credentials.chmod(0o600)
            json.dump(tokens, stream)
    server = ReviewServer(ReviewStore(args.directory / "review.sqlite"), port=args.port, **tokens)
    entry = server.origin + "/#" + server.reviewer_token
    (args.directory / "reviewer-entry.txt").write_text(entry)
    print("Review inbox listening at " + server.origin, flush=True)
    server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
