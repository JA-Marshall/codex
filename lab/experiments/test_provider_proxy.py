from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from provider_proxy import Journal, Proxy
from provider_rate_limit import PacedWindow, SharedLimiter, retry_after


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with self.server.lock:
            self.server.calls.append((time.monotonic(), self.path, body, self.headers["Authorization"]))
        if body == b"cooldown":
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(b'{"error":"limited"}')
        elif body == b"stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: first\n\n")
            self.wfile.flush()
            self.server.release.wait(3)
            self.wfile.write(b"data: last\n\n")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self.upstream.calls, self.upstream.lock = [], threading.Lock()
        self.upstream.release = threading.Event()
        self.journal = Journal(Path(self.temp.name) / "events.jsonl")
        self.limiter = SharedLimiter(5, window=0.2, startup_delay=0)
        self.proxy = Proxy(0, f"http://127.0.0.1:{self.upstream.server_port}/v1", "test-secret", self.limiter, self.journal)
        for server in (self.upstream, self.proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.upstream.release.set()
        self.limiter.stop()
        for server in (self.proxy, self.upstream):
            server.shutdown()
            server.server_close()
        self.journal.stream.close()

    def request(self, body=b"ok", path="/v1/responses", key="test-secret"):
        client = http.client.HTTPConnection("127.0.0.1", self.proxy.server_port, timeout=4)
        client.request("POST", path, body, {"Authorization": "Bearer " + key})
        response = client.getresponse()
        value = response.status, response.read()
        client.close()
        return value

    def test_sixteen_independent_clients_share_one_paced_window(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: self.request(), range(16)))
        self.assertEqual(results, [(200, b"ok")] * 16)
        times = sorted(c[0] for c in self.upstream.calls)
        self.assertEqual(len(times), 16)
        for start in times:
            self.assertLessEqual(sum(start <= t < start + 0.195 for t in times), 5)
        self.assertTrue(all(c[3] == "Bearer test-secret" for c in self.upstream.calls))
        self.assertNotIn("test-secret", (Path(self.temp.name) / "events.jsonl").read_text())

    def test_429_is_forwarded_and_cools_down_other_clients_without_proxy_retry(self):
        self.assertEqual(self.request(b"cooldown"), (429, b'{"error":"limited"}'))
        started = time.monotonic()
        self.assertEqual(self.request(path="/v1/responses/compact"), (200, b"ok"))
        self.assertGreaterEqual(time.monotonic() - started, 0.9)
        self.assertEqual(len(self.upstream.calls), 2)
        self.assertEqual(self.upstream.calls[-1][1], "/v1/responses/compact")

    def test_sse_is_delivered_before_upstream_finishes(self):
        client = http.client.HTTPConnection("127.0.0.1", self.proxy.server_port, timeout=1)
        client.request("POST", "/v1/responses", b"stream", {"Authorization": "Bearer test-secret"})
        response = client.getresponse()
        self.assertEqual(response.read1(100), b"data: first\n\n")
        self.upstream.release.set()
        self.assertEqual(response.read(), b"data: last\n\n")
        client.close()

    def test_cancelled_waiter_does_not_reach_upstream(self):
        self.limiter.cooldown(0.5)
        client = socket.create_connection(("127.0.0.1", self.proxy.server_port))
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer test-secret\r\nContent-Length: 2\r\n\r\nok")
        client.close()
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            events = (Path(self.temp.name) / "events.jsonl").read_text()
            if "request_cancelled" in events:
                break
            time.sleep(0.01)
        self.assertIn("request_cancelled", events)
        self.assertEqual(self.upstream.calls, [])

    def test_invalid_auth_and_unknown_routes_are_not_forwarded(self):
        self.assertEqual(self.request(key="wrong")[0], 401)
        self.assertEqual(self.request(path="/v1/unknown")[0], 404)
        self.assertEqual(self.upstream.calls, [])


class WindowTests(unittest.TestCase):
    def test_long_run_and_restart_have_no_burst_credit(self):
        policy = PacedWindow(100)
        now = 0.0
        observed = []
        for _ in range(500):
            now += policy.delay(now)
            # Account for floating-point boundary rounding without a real sleep.
            now += 0.000001
            observed.append(now)
            policy.record(now)
        for start in observed:
            self.assertLessEqual(sum(start <= t < start + 60 for t in observed), 100)
        restarted = SharedLimiter()
        self.assertGreater(restarted.policy.delay(time.monotonic()), 59)

    def test_retry_after_dates_and_malformed_headers(self):
        self.assertEqual(retry_after("12"), 12)
        self.assertEqual(retry_after("Thu, 01 Jan 1970 00:02:00 GMT", now=60), 60)
        for value in (None, "invalid", "NaN", "Infinity"):
            self.assertEqual(retry_after(value), 60)
        for limit in (0, 101, True, 1.5):
            with self.assertRaises(ValueError):
                PacedWindow(limit)


if __name__ == "__main__":
    unittest.main()
