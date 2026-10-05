"""The frozen worker can import the local SDK under the plain pinned Python."""

import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest

from test_sdk_workflows import SdkFixture, ROOT
from workflows.sdk_freeze import freeze_sdk
from campaign_inputs import freeze, digest
from provider_proxy import Proxy, Journal
from provider_rate_limit import SharedLimiter


class SdkFreezeTest(SdkFixture):
    temporary_parent = Path.home() / ".cache"

    def test_plain_python_frozen_trial_checks_service_and_runs_actual_sdk(self):
        # A local fixture service exercises health/pin checks without live traffic.
        service_dir = self.root / "service"
        service_dir.mkdir()
        journal = Journal(service_dir / "proxy.jsonl")
        proxy = Proxy(
            0, self.mock.url + "/v1", "mock", SharedLimiter(startup_delay=0), journal
        )
        thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(journal.stream.close)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        url = f"http://127.0.0.1:{proxy.server_port}/v1"
        for name in ("provider_proxy.py", "provider_rate_limit.py"):
            shutil.copyfile(ROOT / "lab/experiments" / name, service_dir / name)
        receipt = {
            "schema_version": 1,
            "base_url": url,
            "requests_per_minute": 100,
            "upstream": "https://api.meta.ai/v1",
            "proxy_directory": str(service_dir),
            "source_sha256": {
                name: digest(service_dir / name)
                for name in ("provider_proxy.py", "provider_rate_limit.py")
            },
        }
        (service_dir / "service.json").write_text(json.dumps(receipt))
        home = self.root / "home"
        home.mkdir()
        (home / "config.toml").write_text(
            f'model = "mock-model"\nmodel_provider = "fixture"\nmodel_reasoning_effort = "medium"\n[model_providers.fixture]\nbase_url = "{url}"\n'
        )
        settings = self.root / "sdk.json"
        settings.write_text(
            json.dumps(
                {
                    "sdk_source": str(ROOT / "sdk/python/src"),
                    "source_commit": self.pin.source_commit,
                    "budget": {"requests": 8, "tokens": 1000000, "seconds": 30},
                    "bmad_source": "/home/james/.cache/codex-lab-bmad/v6.12.0",
                    "uv": "/home/james/.local/share/codex-lab-toolchain/bin/uv",
                    "service_key_env": "SDK_TRIAL_TEST_KEY",
                    "interaction_policy": "delegated-task-v1",
                }
            )
        )
        alias = self.root / "codex-linux-sandbox"
        alias.symlink_to(self.pin.binary)
        args = SimpleNamespace(
            binary=Path(self.pin.binary),
            codex_home=home,
            instruction_root=ROOT / "lab",
            sandbox=alias,
            catalog=ROOT / "lab/sdk-workflows.toml",
            output=self.root / "campaign",
            workflow=["direct-v1"],
            fixture=["py-log-tally"],
            repetitions=1,
            jobs=1,
            max_amendments=0,
            task_root=ROOT / "lab/tasks",
            task_toolchain=None,
            task_just=None,
            provider_service=service_dir / "service.json",
            sdk_config=settings,
        )
        manifest = freeze(args)
        (args.output / "trials/trial-0001").mkdir(parents=True)
        (args.output / "runs").mkdir()
        self.response("Unimplemented product is done, according to the model.")
        env = {
            **os.environ,
            "SDK_TRIAL_TEST_KEY": "mock",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        command = [
            manifest["python"],
            "-B",
            str(Path(manifest["archive"]) / "experiments/run_campaign.py"),
            "--trial",
            str(args.output / "campaign.json"),
            "--run-id",
            "trial-0001",
            "--manifest-sha256",
            digest(args.output / "campaign.json"),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=60, env=env
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads((args.output / "trials/trial-0001/result.json").read_text())
        self.assertEqual(result["workflow_result"]["stop_status"], "confirmed", result)
        self.assertEqual(
            result["workflow_result"]["evaluation_status"], "completed", result
        )
        self.assertIs(result["task_success"], False, result)
        runtime = result["workflow_result"]["evidence"]["runtime"]
        self.assertEqual(runtime["interactions"]["policy"], "delegated-task-v1")
        self.assertEqual(len(self.mock.requests()), 1)

    def test_frozen_dependencies_work_without_the_temporary_uv_environment(self):
        archive = self.root / "inputs/lab"
        archive.mkdir(parents=True)
        home = self.root / "profile"
        home.mkdir()
        (home / "config.toml").write_text('model_reasoning_effort = "high"\n')
        manifest = {
            "binary": self.pin.binary,
            "codex_home": str(home),
            "archive": str(archive),
            "jobs": 2,
            "trials": [
                {"workflow": "direct-v1"},
                {"workflow": "bmad-build-auto-v6.12.0"},
            ],
            "provider_service": {"base_url": "http://127.0.0.1:1/v1"},
            "task_ids": ["probe"],
            "pins": {},
        }
        settings = self.root / "sdk.json"
        settings.write_text(
            json.dumps(
                {
                    "sdk_source": str(ROOT / "sdk/python/src"),
                    "source_commit": self.pin.source_commit,
                    "budget": {"requests": 20, "tokens": 1000000, "seconds": 60},
                    "bmad_source": "/home/james/.cache/codex-lab-bmad/v6.12.0",
                    "uv": "/home/james/.local/share/codex-lab-toolchain/bin/uv",
                    "service_key_env": "MODEL_API_KEY",
                }
            )
        )
        freeze_sdk(manifest, settings)
        config = manifest["sdk_runtime"]
        code = f"import sys; sys.path[:0] = {[config['sdk_source'], config['sdk_dependencies']]!r}; import pydantic; from openai_codex.client import CodexClient; print(pydantic.__version__)"
        completed = subprocess.run(
            [str(Path(sys.executable).resolve()), "-I", "-B", "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            completed.stdout.strip(), config["dependency_versions"]["pydantic"]
        )
        self.assertEqual(config["reasoning_effort"], "high")
        self.assertIn(
            str(Path(config["sdk_source"]) / "openai_codex/client.py"), manifest["pins"]
        )


if __name__ == "__main__":
    unittest.main()
