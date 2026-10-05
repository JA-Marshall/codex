"""Finite host-side admission for the original legacy procedural workflow."""

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import sys
import threading
import time
import tomllib

from campaign_inputs import digest, write_json
from campaign_service import endpoint
from provider_proxy import Journal, Proxy
from provider_rate_limit import SharedLimiter
from workflows.session_process import SessionProcess
from workflows.filesystem import SessionSandbox
from workflows.usage import Budget, UsageLedger


@dataclass(frozen=True)
class LegacyPin:
    binary: str
    binary_sha256: str
    python_sha256: str
    unshare_sha256: str
    launcher_sha256: str

    @classmethod
    def capture(cls, binary):
        launcher = Path(__file__).with_name("namespace_exec.py")
        return cls(
            str(Path(binary).resolve()),
            digest(binary),
            digest(sys.executable),
            digest("/usr/bin/unshare"),
            digest(launcher),
        )

    def verify(self):
        if sys.platform != "linux" or self != self.capture(self.binary):
            raise ValueError("legacy namespace runtime changed or unsupported platform")


@dataclass(frozen=True)
class LegacySandbox(SessionSandbox):
    private_root: Path | None = None

    def wrap(self, binary, home, command):
        args = super().wrap(binary, home, command)
        # Legacy scope canonicalizes its deny root. Supply an empty directory,
        # never the grader tree, so the deny declaration remains valid.
        args[args.index("--") : args.index("--")] = ["--dir", str(self.private_root)]
        record_path = home / "outer-sandbox.json"
        record = json.loads(record_path.read_text())
        record.update(argv=args, empty_private_root=str(self.private_root))
        write_json(record_path, record)
        return args


class LegacyMeter:
    def __init__(self, manifest, entry, directory, upstream_key):
        self.manifest, self.entry = manifest, entry
        self.artifacts = Path(directory) / "legacy-meter"
        self.artifacts.mkdir(exist_ok=False)
        self.runs = self.artifacts / "runs"
        self.runs.mkdir()
        upstream = manifest["provider_service"]["base_url"]
        endpoint(upstream)
        self.journal = Journal(self.artifacts / "usage.jsonl")
        self.proxy_journal = Journal(self.artifacts / "proxy.jsonl")
        self.ledger = UsageLedger(
            entry["run_id"],
            manifest["requested_model"],
            Budget(**manifest["legacy_runtime"]["budget"]),
            self.journal,
        )
        self.ledger.register("legacy-host")
        self.client_key = secrets.token_hex(32)
        self.proxy = Proxy(
            0,
            upstream,
            upstream_key,
            SharedLimiter(startup_delay=0),
            self.proxy_journal,
            observer=self,
            client_key=self.client_key,
        )
        self.server = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        self.finished = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.result = None
        try:
            pin = LegacyPin.capture(manifest["binary"])
            sandbox = LegacySandbox(
                Path(directory) / "fixture/repository",
                controls=(self.runs,),
                tools=(
                    Path(manifest["catalog"]),
                    Path(manifest["archive"]) / "instructions",
                    Path(directory) / "policy.json",
                ),
                private_root=Path(manifest["task_root"]),
            )
            self.process = SessionProcess(
                pin,
                self.artifacts / "home",
                self.artifacts / "namespace.json",
                sandbox=sandbox,
            )
            original = tomllib.loads(
                (Path(manifest["codex_home"]) / "config.toml").read_text()
            )
            profile = copy.deepcopy(original)
            provider = profile["model_providers"][profile["model_provider"]]
            if (
                provider.get("base_url") != upstream
                or provider.get("wire_api") != "responses"
                or not provider.get("env_key")
            ):
                raise ValueError(
                    "legacy provider must match the frozen shared Responses service"
                )
            if (
                len(profile["model_providers"]) != 1
                or provider.get("http_headers")
                or provider.get("env_http_headers")
                or provider.get("experimental_bearer_token")
                or provider.get("requires_openai_auth")
            ):
                raise ValueError(
                    "legacy profile must use one environment-key provider without alternate credential headers"
                )
            if profile.get("model_catalog_json"):
                catalog = Path(profile["model_catalog_json"])
                if not catalog.is_absolute():
                    catalog = Path(manifest["codex_home"]) / catalog
                data = catalog.read_bytes()
                if len(data) > 16 * 1024 * 1024:
                    raise ValueError("model catalog exceeds bound")
                target = self.process.home / "model-catalog.json"
                target.write_bytes(data)
                profile["model_catalog_json"] = str(target)
            provider["base_url"] = f"http://127.0.0.1:{self.proxy.server_port}/v1"
            provider["env_key"] = "LAB_LEGACY_PROVIDER_KEY"
            # Serialize the existing profile semantically unchanged except for its
            # per-run endpoint and ephemeral credential variable. No workflow edits.
            sections = []

            def emit(table, names=()):
                if names:
                    sections.append(
                        "[" + ".".join(json.dumps(name) for name in names) + "]"
                    )
                for key, value in table.items():
                    if not isinstance(value, dict):
                        sections.append(json.dumps(key) + "=" + json.dumps(value))
                sections.append("")
                for key, value in table.items():
                    if isinstance(value, dict):
                        emit(value, (*names, key))

            emit(profile)
            text = "\n".join(sections)
            if tomllib.loads(text) != profile:
                raise ValueError("provider profile cannot be preserved exactly")
            (self.process.home / "config.toml").write_text(text)
            self.profile_sha256 = digest(self.process.home / "config.toml")
        except BaseException:
            self.proxy.server_close()
            self.journal.stream.close()
            self.proxy_journal.stream.close()
            raise

    def prepare(self, request_id, body, headers, path):
        # Each authenticated per-run endpoint belongs to one original host.
        # All its planning, implementation, verification and compact calls share
        # one ledger; a caller cannot choose another worker or another budget.
        if headers.get("X-Lab-Worker") not in (None, "legacy-host"):
            raise ValueError("foreign legacy worker attribution")
        return self.ledger.prepare(
            request_id, body, {"X-Lab-Worker": "legacy-host"}, path
        )

    def _monitor(self):
        while not self.finished.wait(0.05):
            if time.monotonic() >= self.ledger.deadline:
                self.ledger.stop("project_deadline")

    def start(self):
        self.server.start()
        self.monitor.start()
        return self

    def command(self, original):
        command = list(original)
        index = command.index("--codex-home")
        command[index + 1] = str(self.process.home)
        return self.process.launch_args(
            command=command, legacy_provider_key=self.client_key
        )

    def close(self):
        if self.result is not None:
            return self.result
        self.ledger.stop("legacy_host_finished_or_deadline")
        if self.server.is_alive():
            self.proxy.shutdown()
        self.proxy.server_close()
        handlers = self.proxy.wait_for_idle(5)
        self.finished.set()
        if self.monitor.ident is not None:
            self.monitor.join(timeout=1)
        if self.server.ident is not None:
            self.server.join(timeout=1)
        stopped = self.process.stopped()
        self.result = dict(
            usage=self.ledger.snapshot(),
            provider_handlers_stopped=handlers,
            namespace_stopped=stopped,
            namespace=self.process.identity,
            runtime=self.process.evidence(),
            effective_profile_sha256=self.profile_sha256,
            deadline_reached=time.monotonic() >= self.ledger.deadline,
            policy="original legacy workflow; added aggregate provider admission and PID-namespace deadline boundary",
        )
        write_json(self.artifacts / "result.json", self.result)
        if handlers:
            self.journal.stream.close()
            self.proxy_journal.stream.close()
        return self.result
