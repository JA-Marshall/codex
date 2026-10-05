"""Run a finite, offline SDK/worker/provider compatibility probe; no live model."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk/python/src"))
sys.path.insert(0, str(ROOT / "sdk/python/tests"))

from app_server_harness import (
    MockResponsesServer,
    sse,
    ev_response_created,
    ev_function_call,
    ev_completed,
)
from provider_rate_limit import SharedLimiter
from workflows.metered_run import MeteredRun
from workflows.session_process import RuntimePin
from workflows.usage import Budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=False)
    workspace = args.artifacts / "workspace"
    workspace.mkdir()
    pin = RuntimePin.capture(args.binary, args.source_commit)
    (args.artifacts / "runtime-pin.json").write_text(
        json.dumps(asdict(pin), indent=2) + "\n"
    )
    with MockResponsesServer() as mock:
        mock.enqueue_sse(
            sse(
                [
                    ev_response_created("dispatch"),
                    ev_function_call(
                        "four-reviewers",
                        "run_workers",
                        json.dumps(
                            {
                                "workers": [
                                    {
                                        "prompt": f"Review layer {i}; report observations only."
                                    }
                                    for i in range(4)
                                ]
                            }
                        ),
                    ),
                    ev_completed("dispatch"),
                ]
            )
        )
        for i in range(4):
            mock.enqueue_assistant_message(f"review-{i}", response_id=f"review-{i}")
        mock.enqueue_assistant_message("review group complete", response_id="parent")
        mock.enqueue_assistant_message("continuation complete", response_id="continued")
        run = MeteredRun(
            run_id="offline-sdk-probe",
            pin=pin,
            workspace=workspace,
            artifacts=args.artifacts / "run",
            model="mock-model",
            budget=Budget(10, 1000000, 60),
            shared_upstream=mock.url + "/v1",
            upstream_key="mock",
            limiter=SharedLimiter(startup_delay=0, window=0.1),
        )
        try:
            run.start()
            parent = run.parent(
                "Dispatch the four independent review layers and await them."
            )
            child = run.bridge.continue_worker(
                next(iter(run.bridge.children)), "Continue your own review."
            )
        finally:
            result = run.close()
        summary = {
            "kind": "offline_mock_provider",
            "parent": parent,
            "continued": child,
            "requests": len(mock.requests()),
            "runtime": result,
        }
        (args.artifacts / "probe.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "requests": summary["requests"],
                    "stop": result["process"]["stop_status"],
                    "tokens": result["usage"]["observed_tokens"],
                    "artifacts": str(args.artifacts),
                }
            )
        )
        if (
            parent["status"] != "completed"
            or child["status"] != "completed"
            or result["process"]["stop_status"] != "confirmed"
            or result["usage"]["in_flight"]
            or result["usage"]["unknown_requests"]
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
