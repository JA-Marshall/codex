"""Local SDK sessions with bounded callbacks and separately recorded stop proof."""

import json
from pathlib import Path
import threading
import time

from openai_codex.client import CodexClient, CodexConfig
from pydantic import BaseModel, ConfigDict

from provider_proxy import Journal
from workflows.callbacks import CallbackPool
from workflows.fidelity import Fidelity
from workflows.session_process import SessionProcess


class ObjectResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class SdkSession:
    def __init__(
        self,
        *,
        pin,
        workspace,
        artifacts,
        model,
        provider,
        endpoint,
        seconds=300,
        callback=None,
        sandbox=None,
        reasoning_effort="medium",
        model_catalog=None,
        clock=None,
    ):
        if not model or not provider or not 0 < seconds <= 86400:
            raise ValueError("explicit model/provider and finite deadline required")
        self.workspace = str(Path(workspace).resolve())
        self.artifacts = Path(artifacts)
        self.artifacts.mkdir(parents=True, exist_ok=False)
        self.journal = Journal(self.artifacts / "session.jsonl")
        self.fidelity = Fidelity(self.artifacts / "invocations.jsonl")
        self.process = SessionProcess(
            pin,
            self.artifacts / "home",
            self.artifacts / "namespace.json",
            sandbox=sandbox,
        )
        if model_catalog is not None:
            data = Path(model_catalog).read_bytes()
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("model catalog exceeds limit")
            catalog = self.process.home / "model-catalog.json"
            catalog.write_bytes(data)
            (self.process.home / "config.toml").write_text(
                "model_catalog_json = " + json.dumps(str(catalog)) + "\n"
            )
        self.model, self.provider, self.endpoint = model, provider, endpoint
        self.reasoning_effort = reasoning_effort
        self.callback = callback
        self.guard = threading.RLock()
        self.threads = {}
        self.active = {}
        self.cancelled = threading.Event()
        self.closed = threading.Event()
        self.clock = clock
        self._deadline = time.monotonic() + seconds
        self.work_admission = threading.Event()
        self.work_admission.set()
        self.executor = CallbackPool()
        self.client = CodexClient(
            CodexConfig(
                cwd=self.workspace, launch_args_override=self.process.launch_args()
            ),
            approval_handler=self._callback,
            server_request_executor=self.executor,
        )
        self.watchdog = threading.Thread(target=self._watch, daemon=True)
        self.stop_receipt = None
        self.start_attempted = False
        self.close_lock = threading.Lock()

    @property
    def deadline(self):
        return self.clock.deadline if self.clock else self._deadline

    @deadline.setter
    def deadline(self, value):
        if self.clock is not None:
            raise RuntimeError("human trial deadline belongs to its shared clock")
        self._deadline = value

    def start(self):
        if self.closed.is_set() or self.cancelled.is_set():
            raise RuntimeError("a closed study session cannot restart")
        try:
            self.start_attempted = True
            self.client.start()
            self.watchdog.start()
            initialized = self.client.initialize()
            self.process.launched()
            self.journal.event(
                "session_started",
                **self.process.evidence(),
                server=initialized.model_dump(mode="json"),
            )
            return self
        except BaseException:
            self.close()
            raise

    def _callback(self, method, params):
        if self.cancelled.is_set() or self.closed.is_set():
            raise RuntimeError("session stopped")
        if method in ("item/tool/call", "item/tool/requestUserInput") and self.callback:
            return self.callback(method, params)
        # Do not inherit the SDK's permissive default approval handler.
        if method in (
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        ):
            return {"decision": "decline"}
        raise RuntimeError("unsupported server request")

    def request(self, method, params):
        return self.client.request(
            method, params, response_model=ObjectResponse
        ).model_dump(mode="json")

    def new_thread(self, worker_id, *, tools=None, writable=False, role=None):
        with self.guard:
            if not self.work_admission.is_set():
                raise RuntimeError("trial is pausing or awaiting human input")
            if role not in (None, "planner") or (
                role == "planner" and (writable or self.process.sandbox is None)
            ):
                raise ValueError(
                    "planner needs explicit control-only sandbox permissions"
                )
            if (
                self.cancelled.is_set()
                or self.closed.is_set()
                or worker_id in self.threads
            ):
                raise RuntimeError("worker cannot be admitted")
            # The host supplies one registered, metered endpoint per worker.
            connection = self.endpoint(worker_id)
            params = {
                "model": self.model,
                "modelProvider": self.provider,
                "allowProviderModelFallback": False,
                "cwd": self.workspace,
                "approvalPolicy": "never",
                "sandbox": "workspace-write" if writable else "read-only",
                "ephemeral": True,
                "dynamicTools": tools or [],
                "config": {
                    "model_reasoning_effort": self.reasoning_effort,
                    "features.multi_agent": False,
                    "features.multi_agent_v2": False,
                    "features.default_mode_request_user_input": True,
                    "web_search": "disabled",
                    "sandbox_workspace_write.exclude_slash_tmp": True,
                    "sandbox_workspace_write.exclude_tmpdir_env_var": True,
                    f"model_providers.{self.provider}": {
                        "name": "Metered study provider",
                        "base_url": connection["url"],
                        "http_headers": connection["headers"],
                        "wire_api": "responses",
                        "request_max_retries": 0,
                        "stream_max_retries": 0,
                        "requires_openai_auth": False,
                    },
                },
            }
            if self.process.sandbox is not None:
                permissions = self.process.sandbox.thread_permissions(
                    self.process.home, writable, role=role
                )
                params.pop("sandbox")
                params["permissions"] = permissions["permissions"]
                params["config"].update(permissions["config"])
            result = self.client.thread_start(params)
            actual = result.model_dump(mode="json", by_alias=True)
            if (
                actual["model"] != self.model
                or actual["modelProvider"] != self.provider
            ):
                self.cancelled.set()
                raise RuntimeError("resolved model/provider mismatch")
            self.threads[worker_id] = result.thread.id
            self.journal.event(
                "worker_started",
                worker_id=worker_id,
                thread_id=result.thread.id,
                model=actual["model"],
                provider=actual["modelProvider"],
            )
            return worker_id

    def turn(self, worker_id, prompt):
        if not isinstance(prompt, str) or len(prompt.encode()) > 256 * 1024:
            raise ValueError("worker prompt exceeds limit")
        with self.guard:
            if not self.work_admission.is_set():
                raise RuntimeError("trial is pausing or awaiting human input")
            if (
                self.cancelled.is_set()
                or self.closed.is_set()
                or worker_id in self.active
            ):
                raise RuntimeError("worker unavailable")
            thread_id = self.threads[worker_id]
            self.fidelity.record(
                "turn_prompt", worker_id=worker_id, thread_id=thread_id, prompt=prompt
            )
            started = self.client.turn_start(
                thread_id,
                prompt,
                {"model": self.model, "effort": self.reasoning_effort},
            )
            turn_id = started.turn.id
            self.active[worker_id] = turn_id
        self.journal.event(
            "turn_started", worker_id=worker_id, thread_id=thread_id, turn_id=turn_id
        )
        output = []
        retained = 0
        try:
            while True:
                event = self.client.next_turn_notification(turn_id)
                payload = event.payload
                data = (
                    payload.model_dump(mode="json", by_alias=True)
                    if hasattr(payload, "model_dump")
                    else {}
                )
                # Keep lifecycle evidence compact. Full command output and model
                # deliberation are deliberately not copied into another trace.
                if event.method == "item/completed":
                    item = data.get("item", {})
                    if item.get("type") == "commandExecution":
                        self.fidelity.record(
                            "command",
                            worker_id=worker_id,
                            turn_id=turn_id,
                            command=item.get("command"),
                            cwd=item.get("cwd"),
                            status=item.get("status"),
                            exit_code=item.get("exitCode"),
                        )
                    if item.get("type") == "agentMessage":
                        text = item.get("text", "")
                        retained += len(text.encode())
                        if retained > 256 * 1024:
                            self.cancelled.set()
                            raise RuntimeError("worker result exceeds limit")
                        output.append(text)
                if event.method == "turn/completed":
                    status = data["turn"]["status"]
                    raw_error = data["turn"].get("error")
                    error = None
                    if isinstance(raw_error, dict):
                        error = {}
                        for name, limit in (
                            ("message", 2048),
                            ("codexErrorInfo", 1024),
                            ("additionalDetails", 1024),
                        ):
                            value = raw_error.get(name)
                            encoded = json.dumps(value, ensure_ascii=False).encode()
                            error[name] = (
                                value
                                if len(encoded) <= limit
                                else {
                                    "truncated": True,
                                    "prefix": encoded[:limit].decode(
                                        "utf-8", errors="ignore"
                                    ),
                                }
                            )
                    self.journal.event(
                        "turn_completed",
                        worker_id=worker_id,
                        turn_id=turn_id,
                        status=status,
                        error=error,
                    )
                    return {
                        "worker_id": worker_id,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "status": status,
                        "error": error,
                        "text": "\n".join(output),
                    }
        finally:
            with self.guard:
                self.active.pop(worker_id, None)
            self.client.unregister_turn_notifications(turn_id)

    def steer(self, worker_id, text):
        with self.guard:
            if not self.work_admission.is_set():
                raise RuntimeError("trial is pausing or awaiting human input")
            thread_id, turn_id = self.threads[worker_id], self.active[worker_id]
        self.client.turn_steer(thread_id, turn_id, text)
        self.journal.event("user_response", worker_id=worker_id, turn_id=turn_id)

    def interrupt(self):
        self.cancelled.set()
        with self.guard:
            active = [
                (worker, self.threads[worker], turn)
                for worker, turn in self.active.items()
            ]
        for worker, thread, turn in active:
            try:
                self.client.turn_interrupt(thread, turn)
                self.journal.event(
                    "interrupt_acknowledged", worker_id=worker, turn_id=turn
                )
            except Exception:
                self.journal.event(
                    "interrupt_unconfirmed", worker_id=worker, turn_id=turn
                )

    def _watch(self):
        while not self.closed.wait(0.05):
            if self.cancelled.is_set() or time.monotonic() >= self.deadline:
                threading.Thread(target=self.interrupt, daemon=True).start()
                if not self.closed.wait(3):
                    self.client.close()
                return

    def close(self):
        with self.close_lock:
            return self._close()

    def _close(self):
        if self.stop_receipt is not None:
            return self.stop_receipt
        cleanup = False
        try:
            self.interrupt()
            deadline = time.monotonic() + 2
            for thread_id in list(self.threads.values()):
                self.request(
                    "thread/backgroundTerminals/clean", {"threadId": thread_id}
                )
            while time.monotonic() < deadline:
                pages = [
                    self.request("thread/backgroundTerminals/list", {"threadId": tid})
                    for tid in self.threads.values()
                ]
                if all(
                    isinstance(page.get("data"), list)
                    and not page["data"]
                    and "nextCursor" in page
                    and page["nextCursor"] is None
                    for page in pages
                ):
                    cleanup = True
                    break
                time.sleep(0.02)
        except Exception:
            pass
        finally:
            self.client.close()
            stopped = self.process.stopped() if self.start_attempted else True
            self.closed.set()
            callbacks_stopped = self.executor.close()
        self.stop_receipt = {
            "schema_version": 1,
            "start_attempted": self.start_attempted,
            "background_terminals_empty": cleanup,
            "callbacks_stopped": callbacks_stopped,
            "stop_status": "confirmed"
            if stopped and callbacks_stopped
            else "unconfirmed",
            "process_stop": "not_started"
            if not self.start_attempted
            else "confirmed"
            if stopped
            else "unconfirmed",
            **self.process.evidence(),
        }
        self.journal.event("session_stopped", **self.stop_receipt)
        (self.artifacts / "stop.json").write_text(
            json.dumps(self.stop_receipt, indent=2) + "\n"
        )
        self.journal.stream.close()
        return self.stop_receipt
