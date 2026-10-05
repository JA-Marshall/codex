"""Exercise LAN boundary behavior against the real read-only observer handler."""

from http.client import HTTPConnection
import json
from threading import Lock, Thread
import unittest

from lan_proxy import make_proxy
from server import make_server


class Store:
    lock = Lock()

    def list_campaigns(self):
        return [{"id": "smoke", "state": "prepared"}]

    def campaign(self, campaign_id):
        if campaign_id != "smoke":
            raise FileNotFoundError
        return {"id": campaign_id, "trials": []}


class LanProxyTests(unittest.TestCase):
    def setUp(self):
        self.backend = make_server(Store(), port=0)
        self.proxy = make_proxy(
            "127.0.0.1", "127.0.0.1/32", port=0, upstream_port=self.backend.server_port
        )
        self.threads = []
        for server in (self.backend, self.proxy):
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            self.threads.append(thread)

    def tearDown(self):
        for server in (self.proxy, self.backend):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def request(self, method, path, host=None, source_address=None):
        connection = HTTPConnection(
            "127.0.0.1",
            self.proxy.server_port,
            timeout=2,
            source_address=source_address,
        )
        try:
            headers = {} if host is None else {"Host": host}
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_reads_and_head_preserve_response_and_writes_are_rejected(self):
        status, headers, payload = self.request("GET", "/api/campaigns/smoke")
        self.assertEqual(
            (status, json.loads(payload)), (200, {"id": "smoke", "trials": []})
        )
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        status, head_headers, head_body = self.request("HEAD", "/api/campaigns/smoke")
        self.assertEqual(
            (status, head_headers["Content-Length"], head_body),
            (200, str(len(payload)), b""),
        )
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, "/api/campaigns/smoke")
                self.assertEqual(
                    (status, headers["Allow"], body), (405, "GET, HEAD", b"")
                )

    def test_host_client_and_path_boundaries(self):
        for host, path, expected in (
            ("attacker.invalid", "/api/campaigns", 403),
            ("localhost", "/api/campaigns", 403),
            ("127.0.0.1", "/api/campaigns", 200),
            (None, "/campaign.json", 404),
            (None, "/api/campaigns/%2e%2e%2foutside", 404),
            ("127.0.0.1", "http://attacker.invalid/api/campaigns", 404),
            (None, "/api/campaigns/unknown", 404),
        ):
            with self.subTest(host=host, path=path):
                self.assertEqual(self.request("GET", path, host)[0], expected)
        self.assertEqual(
            self.request("GET", "/api/campaigns", source_address=("127.0.0.2", 0))[0],
            403,
        )

    def test_unavailable_loopback_observer_returns_502(self):
        self.backend.shutdown()
        self.backend.server_close()
        status, _, body = self.request("GET", "/api/campaigns")
        self.assertEqual(status, 502)
        self.assertIn(b"The local dashboard is unavailable", body)


if __name__ == "__main__":
    unittest.main()
