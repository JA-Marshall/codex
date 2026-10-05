"""Exercise provider order and credentials with real loopback HTTP servers."""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from provider_failover import ZenProvider
from provider_proxy import Journal, Proxy
from provider_rate_limit import SharedLimiter


class FakeProvider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.calls.append(
            (self.path, self.headers["Authorization"], json.loads(body))
        )
        status = self.server.statuses.pop(0) if self.server.statuses else 200
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        if self.server.retry_after:
            self.send_header("Retry-After", self.server.retry_after)
        if self.server.truncate:
            self.send_header("Content-Length", "1000")
        self.end_headers()
        self.wfile.write(b"data: " + self.server.label + b"\n\n")
        self.wfile.flush()
        if self.server.stream:
            self.server.release.wait(3)
            self.wfile.write(b"data: done\n\n")
        self.close_connection = True


class FailoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Journal(Path(self.temp.name) / "events.jsonl")
        self.meta = self.provider(b"meta")
        self.zen = self.provider(b"zen")
        self.limiter = SharedLimiter(100, window=0.01, startup_delay=0)
        self.primary = ZenProvider(
            f"http://127.0.0.1:{self.zen.server_port}/zen/v1", "zen-secret"
        )
        self.proxy = Proxy(
            0,
            f"http://127.0.0.1:{self.meta.server_port}/v1",
            "meta-secret",
            self.limiter,
            self.journal,
            self.primary,
        )
        threading.Thread(target=self.proxy.serve_forever, daemon=True).start()

    def provider(self, label):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        server.daemon_threads = True
        server.label, server.calls, server.statuses = label, [], []
        server.retry_after, server.truncate, server.stream = None, False, False
        server.release = threading.Event()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def tearDown(self):
        self.limiter.stop()
        for server in (self.proxy, self.zen, self.meta):
            if hasattr(server, "release"):
                server.release.set()
            server.shutdown()
            server.server_close()
        self.journal.stream.close()

    def request(
        self,
        path="/v1/responses",
        model="muse-spark-1.3-contributor",
        key="meta-secret",
    ):
        client = http.client.HTTPConnection(
            "127.0.0.1", self.proxy.server_port, timeout=5
        )
        client.request(
            "POST",
            path,
            json.dumps({"model": model, "input": "hi", "stream": True}),
            {"Authorization": "Bearer " + key},
        )
        response = client.getresponse()
        result = response.status, response.read()
        client.close()
        return result

    def test_zen_first_with_own_key_and_model_alias(self):
        self.assertEqual(self.request(), (200, b"data: zen\n\n"))
        self.assertEqual(self.meta.calls, [])
        self.assertEqual(
            self.zen.calls,
            [
                (
                    "/zen/v1/responses",
                    "Bearer zen-secret",
                    {
                        "model": "muse-spark-1.3-contributor-free",
                        "input": "hi",
                        "stream": True,
                    },
                )
            ],
        )
        events = (Path(self.temp.name) / "events.jsonl").read_text()
        self.assertNotIn("zen-secret", events)
        self.assertNotIn("meta-secret", events)

    def test_bounded_retry_then_meta_preserves_original_body_and_key(self):
        self.zen.statuses = [503, 503]
        self.zen.retry_after = "0"
        self.assertEqual(self.request(), (200, b"data: meta\n\n"))
        self.assertEqual(len(self.zen.calls), 2)
        self.assertEqual(
            self.meta.calls,
            [
                (
                    "/v1/responses",
                    "Bearer meta-secret",
                    {
                        "model": "muse-spark-1.3-contributor",
                        "input": "hi",
                        "stream": True,
                    },
                )
            ],
        )

    def test_billing_failure_and_long_rate_limit_skip_retries(self):
        for status in (402, 429):
            with self.subTest(status=status):
                self.primary.blocked_until = 0
                self.zen.calls.clear()
                self.zen.statuses = [status]
                self.zen.retry_after = "60"
                self.assertEqual(self.request(), (200, b"data: meta\n\n"))
                self.assertEqual(len(self.zen.calls), 1)
                self.assertEqual(self.request(), (200, b"data: meta\n\n"))
                self.assertEqual(len(self.zen.calls), 1)

    def test_invalid_request_is_forwarded_without_fallback(self):
        self.zen.statuses = [400]
        self.assertEqual(self.request(), (400, b"data: zen\n\n"))
        self.assertEqual(self.meta.calls, [])

    def test_unknown_model_and_compaction_go_directly_to_meta(self):
        self.assertEqual(self.request(model="unsupported"), (200, b"data: meta\n\n"))
        self.assertEqual(
            self.request(path="/v1/responses/compact"), (200, b"data: meta\n\n")
        )
        self.assertEqual(self.zen.calls, [])

    def test_local_auth_failure_reaches_neither_provider(self):
        self.assertEqual(self.request(key="wrong")[0], 401)
        self.assertEqual((self.zen.calls, self.meta.calls), ([], []))

    def test_connection_failure_falls_back(self):
        self.zen.shutdown()
        self.zen.server_close()
        self.primary.attempts = 1
        self.assertEqual(self.request(), (200, b"data: meta\n\n"))
        self.assertEqual(len(self.meta.calls), 1)

    def test_stream_is_immediate_and_broken_stream_is_never_replayed(self):
        self.zen.stream = True
        client = http.client.HTTPConnection(
            "127.0.0.1", self.proxy.server_port, timeout=1
        )
        client.request(
            "POST",
            "/v1/responses",
            json.dumps({"model": "muse-spark-1.3-contributor"}),
            {"Authorization": "Bearer meta-secret"},
        )
        response = client.getresponse()
        self.assertEqual(response.read1(100), b"data: zen\n\n")
        self.zen.release.set()
        self.assertEqual(response.read(), b"data: done\n\n")
        client.close()
        self.zen.stream, self.zen.truncate = False, True
        # The client receives a closed connection after partial data, not a second model answer.
        self.assertEqual(self.request(), (200, b"data: zen\n\n"))
        self.assertEqual(self.meta.calls, [])


if __name__ == "__main__":
    unittest.main()
