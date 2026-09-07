"""Loopback Responses relay with a shared 100-request/minute ceiling; no retries."""

import argparse
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import signal
import socket
import threading
import time
from urllib.parse import urlsplit
import uuid

from provider_rate_limit import Cancelled, SharedLimiter, retry_after

HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
MAX_BODY = 64 * 1024 * 1024


class Journal:
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf-8")
        self.lock = threading.Lock()

    def event(self, kind, **fields):
        with self.lock:
            self.stream.write(
                json.dumps(dict(type=kind, unix_ms=time.time_ns() // 1000000, **fields))
                + "\n"
            )
            self.stream.flush()


class Proxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port, upstream, key, limiter, journal):
        endpoint = urlsplit(upstream)
        if (
            endpoint.scheme not in ("https", "http")
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or endpoint.path.rstrip("/") != "/v1"
            or (
                endpoint.scheme == "http"
                and endpoint.hostname not in ("127.0.0.1", "localhost")
            )
        ):
            raise ValueError(
                "upstream must be HTTPS /v1 (HTTP permitted only for loopback tests)"
            )
        if not key or any(c in key for c in "\r\n"):
            raise ValueError("provider credential is missing or malformed")
        self.endpoint, self.key, self.limiter, self.journal = (
            endpoint,
            key,
            limiter,
            journal,
        )
        self.capacity = threading.BoundedSemaphore(64)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, address):
        if not self.capacity.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.capacity.release()

    def handle_error(self, request, address):
        # Do not emit request headers, bodies or credential-bearing exceptions.
        self.journal.event("handler_failed")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *_):
        pass

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        if self.path != "/health":
            return self.reply(404, {"error": "unknown route"})
        self.reply(
            200,
            {
                "status": "ready",
                "requests_per_minute": self.server.limiter.policy.limit,
            },
        )

    def disconnected(self):
        readable, _, _ = select.select([self.connection], [], [], 0)
        if not readable:
            return False
        try:
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def do_POST(self):
        if self.path not in ("/v1/responses", "/v1/responses/compact"):
            return self.reply(404, {"error": "unknown route"})
        auth = self.headers.get_all("Authorization", [])
        if len(auth) != 1 or not hmac.compare_digest(
            auth[0].encode(), ("Bearer " + self.server.key).encode()
        ):
            return self.reply(401, {"error": "invalid provider credential"})
        lengths = self.headers.get_all("Content-Length", [])
        if (
            len(lengths) != 1
            or not lengths[0].isascii()
            or not lengths[0].isdigit()
            or self.headers.get("Transfer-Encoding")
        ):
            return self.reply(411, {"error": "one content length required"})
        length = int(lengths[0])
        if length > MAX_BODY:
            return self.reply(413, {"error": "request body exceeds limit"})
        body = self.rfile.read(length)
        if len(body) != length:
            return
        request_id = uuid.uuid4().hex
        journal = self.server.journal
        started = time.monotonic()
        journal.event(
            "request_queued",
            request_id=request_id,
            path=self.path,
            client_request_id=self.headers.get("x-client-request-id", "")[:128],
        )
        endpoint = self.server.endpoint
        connection_type = (
            http.client.HTTPSConnection
            if endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        upstream = connection_type(endpoint.hostname, endpoint.port, timeout=300)
        status = None
        begun = False
        blocked = HOP | {
            v.strip().lower() for v in self.headers.get("Connection", "").split(",")
        }
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in blocked | {"authorization"}
        }
        headers["Authorization"] = "Bearer " + self.server.key
        headers["Content-Length"] = str(len(body))
        try:
            with self.server.limiter.dispatch(self.disconnected):
                journal.event(
                    "request_dispatched",
                    request_id=request_id,
                    queued_ms=round((time.monotonic() - started) * 1000),
                )
                upstream.request("POST", self.path, body=body, headers=headers)
            response = upstream.getresponse()
            status = response.status
            if status == 429 or (status == 503 and response.getheader("Retry-After")):
                delay = retry_after(response.getheader("Retry-After"))
                self.server.limiter.cooldown(delay)
                journal.event(
                    "provider_cooldown",
                    request_id=request_id,
                    status=status,
                    seconds=delay,
                )
            self.send_response(status)
            response_blocked = HOP | {
                v.strip().lower()
                for v in response.getheader("Connection", "").split(",")
            }
            for key, value in response.getheaders():
                if key.lower() not in response_blocked:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            begun = True
            while chunk := response.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
        except Cancelled:
            journal.event("request_cancelled", request_id=request_id)
        except (OSError, http.client.HTTPException):
            journal.event(
                "request_failed", request_id=request_id, upstream_status=status
            )
            if not begun:
                try:
                    self.reply(502, {"error": "provider connection failed"})
                except OSError:
                    pass
        finally:
            upstream.close()
            self.close_connection = True
            journal.event(
                "request_finished",
                request_id=request_id,
                upstream_status=status,
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--upstream", default="https://api.meta.ai/v1")
    parser.add_argument("--requests-per-minute", type=int, default=100)
    parser.add_argument("--key-env", default="MODEL_API_KEY")
    parser.add_argument("--events", type=Path, required=True)
    args = parser.parse_args()
    limiter = SharedLimiter(args.requests_per_minute)
    journal = Journal(args.events)
    server = Proxy(
        args.port, args.upstream, os.environ.get(args.key_env, ""), limiter, journal
    )
    journal.event(
        "proxy_started",
        requests_per_minute=args.requests_per_minute,
        window_seconds=60,
        startup_cooldown_seconds=60,
        port=server.server_port,
        upstream=args.upstream,
        automatic_retries=0,
        source_sha256={
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in ("provider_proxy.py", "provider_rate_limit.py")
        },
    )

    def stop(*_):
        limiter.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(
        json.dumps(
            {
                "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "requests_per_minute": args.requests_per_minute,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        journal.event("proxy_stopped")


if __name__ == "__main__":
    main()
