import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from campaign_inputs import freeze, load_campaign, validate_pins
from campaign_service import check_service, freeze_service, sha256
from run_campaign import coordinate, main


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.server.requests.append(("GET", self.path))
        body = json.dumps(
            {"status": "ready", "requests_per_minute": self.server.rate}
        ).encode()
        self.send_response(self.server.status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CampaignServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
        self.server.rate, self.server.status, self.server.requests = 100, 200, []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.config = {
            "model": "muse-test",
            "model_provider": "test",
            "model_providers": {"test": {"base_url": self.base_url}},
        }
        self.proxy = self.root / "proxy"
        self.proxy.mkdir()
        sources = {}
        for name in ("provider_proxy.py", "provider_rate_limit.py"):
            path = self.proxy / name
            path.write_text("# fixed mock service source\n")
            sources[name] = sha256(path)
        self.receipt = self.proxy / "service.json"
        self.receipt.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "base_url": self.base_url,
                    "requests_per_minute": 100,
                    "upstream": "https://api.meta.ai/v1",
                    "proxy_directory": str(self.proxy),
                    "source_sha256": sources,
                }
            )
        )

    def stop_server(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def test_freeze_is_offline_and_service_sources_are_pinned(self):
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text(
            f'model="muse-test"\nmodel_provider="test"\n[model_providers.test]\nbase_url="{self.base_url}"\n'
        )
        source = Path(__file__).resolve().parents[1]
        args = argparse.Namespace(
            binary=Path(sys.executable),
            sandbox=Path(sys.executable),
            codex_home=home,
            instruction_root=source,
            catalog=source / "workflows/queue-matrix-v2.toml",
            workflow=["queue-aaa-v2"],
            fixture=["durable-queue-v1"],
            repetitions=200,
            jobs=16,
            max_amendments=0,
            output=self.root / "campaign",
            provider_service=self.receipt,
        )
        with patch("http.client.HTTPConnection") as network:
            manifest = freeze(args)
        network.assert_not_called()
        self.assertEqual(manifest["provider_service"]["base_url"], self.base_url)
        self.assertEqual(
            load_campaign(args.output / "campaign.json")["trials"], manifest["trials"]
        )
        self.assertEqual(len(manifest["trials"]), 200)
        check_service(manifest)
        self.assertEqual(self.server.requests, [("GET", "/health")])
        (self.proxy / "provider_proxy.py").write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "input changed"):
            validate_pins(manifest)

    def test_missing_service_direct_routing_and_modified_sources_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "require --provider-service"):
            freeze_service(None, self.config)
        direct = dict(
            self.config,
            model_providers={"test": {"base_url": "https://api.meta.ai/v1"}},
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            freeze_service(self.receipt, direct)
        (self.proxy / "provider_rate_limit.py").write_text("# altered\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            freeze_service(self.receipt, self.config)
        self.assertEqual(self.server.requests, [])

    def test_unready_or_changed_service_stops_before_worker_admission(self):
        service, pins = freeze_service(self.receipt, self.config)
        manifest = {
            "output": str(self.root),
            "pins": pins,
            "provider_service": service,
            "requested_model": "muse-test",
        }
        with patch("run_campaign.worker_command") as worker:
            self.server.status = 503
            with self.assertRaisesRegex(ValueError, "unavailable"):
                coordinate(manifest)
            self.server.status, self.server.rate = 200, 99
            with self.assertRaisesRegex(ValueError, "rate differs"):
                coordinate(manifest)
        worker.assert_not_called()
        self.assertFalse((self.root / "events.jsonl").exists())
        with self.assertRaisesRegex(ValueError, "no pinned"):
            check_service({"requested_model": "muse-test"})

    def test_execute_refuses_old_direct_muse_campaign_before_reexec(self):
        with (
            patch.object(
                sys,
                "argv",
                ["run_campaign.py", "--execute", str(self.root / "old.json")],
            ),
            patch(
                "run_campaign.load_campaign",
                return_value={"requested_model": "muse-test"},
            ),
            patch("run_campaign.os.execv") as reexec,
        ):
            with self.assertRaisesRegex(ValueError, "no pinned"):
                main()
        reexec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
