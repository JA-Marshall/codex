"""BMAD's minimal blocking group and same-worker continuation bridge."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import uuid


WORKER_TOOLS = [
    {
        "name": "run_workers",
        "description": "Run up to four fresh-context workers concurrently; return after all finish.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workers": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "writable": {"type": "boolean"},
                        },
                        "required": ["prompt"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["workers"],
            "additionalProperties": False,
        },
    },
    {
        "name": "continue_worker",
        "description": "Continue an existing worker in its preserved conversation and await completion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "worker_id": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["worker_id", "prompt"],
            "additionalProperties": False,
        },
    },
]


class WorkerBridge:
    def __init__(self, session, *, declare_group):
        self.session = session
        self.declare_group = declare_group
        self.executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="study-worker"
        )
        self.group_slot = threading.Lock()
        self.children = set()
        self.parent_thread = None

    def group(self, workers):
        if not isinstance(workers, list) or not 1 <= len(workers) <= 4:
            raise ValueError("groups require one to four workers")
        if any(
            not isinstance(w, dict)
            or set(w) - {"prompt", "writable"}
            or not isinstance(w.get("prompt"), str)
            or len(w["prompt"].encode()) > 256 * 1024
            or type(w.get("writable", False)) is not bool
            for w in workers
        ):
            raise ValueError("invalid worker input")
        if sum(w.get("writable", False) for w in workers) > 1:
            raise ValueError(
                "parallel writers require later isolated-checkout integration"
            )
        if not self.group_slot.acquire(blocking=False):
            raise RuntimeError("worker group already active")
        futures = []
        try:
            ids = [uuid.uuid4().hex for _ in workers]
            self.declare_group(ids)
            self.session.fidelity.record(
                "worker_group",
                worker_ids=ids,
                writable=[worker.get("writable", False) for worker in workers],
            )
            for worker_id, worker in zip(ids, workers):
                self.session.new_thread(
                    worker_id, writable=worker.get("writable", False)
                )
                self.children.add(worker_id)
                futures.append(
                    self.executor.submit(self.session.turn, worker_id, worker["prompt"])
                )
            # Launch the entire group before waiting for any result.
            return [future.result() for future in futures]
        except BaseException:
            self.session.cancelled.set()
            for future in futures:
                try:
                    future.result()
                except Exception:
                    pass
            raise
        finally:
            self.group_slot.release()

    def continue_worker(self, worker_id, prompt):
        if worker_id not in self.children:
            raise ValueError("unknown child worker")
        if not self.group_slot.acquire(blocking=False):
            raise RuntimeError("worker group already active")
        try:
            return self.session.turn(worker_id, prompt)
        finally:
            self.group_slot.release()

    def callback(self, method, params):
        if method != "item/tool/call" or params.get("threadId") != self.parent_thread:
            raise ValueError("only the owning parent may dispatch children")
        args = params["arguments"]
        if params["tool"] == "run_workers" and set(args) == {"workers"}:
            result = self.group(args["workers"])
        elif params["tool"] == "continue_worker" and set(args) == {
            "worker_id",
            "prompt",
        }:
            result = self.continue_worker(args["worker_id"], args["prompt"])
        else:
            raise ValueError("unsupported worker operation")
        text = json.dumps(result)
        if len(text.encode()) > 256 * 1024:
            raise ValueError("group result exceeds context limit")
        return {"contentItems": [{"type": "inputText", "text": text}], "success": True}

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
