"""Actual sandboxed app-server: private reads, protected skills, and local commits."""

import json
from pathlib import Path
import subprocess
import unittest

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.filesystem import SessionSandbox


class SdkIsolationTest(SdkFixture):
    def test_private_assets_hidden_writer_commits_and_reviewer_cannot_write(self):
        private = self.root / "private"
        private.mkdir()
        secret = private / "evaluator.txt"
        secret.write_text("private-grader-canary-938201")
        (self.workspace / "escape").symlink_to(secret)
        assets = self.workspace / "_bmad"
        assets.mkdir()
        skill = assets / "workflow.md"
        skill.write_text("protected skill")
        script = self.workspace / "probe.py"
        script.write_text(
            "from pathlib import Path\nimport subprocess\n"
            f"for target in [{str(secret)!r}, {'/proc/self/root' + str(secret)!r}, 'escape']:\n"
            "    try: Path(target).read_text()\n"
            "    except (PermissionError, FileNotFoundError): pass\n"
            "    else: raise AssertionError('private data exposed')\n"
            "try: Path('_bmad/workflow.md').write_text('tampered')\n"
            "except (PermissionError, OSError): pass\n"
            "else: raise AssertionError('protected asset writable')\n"
            "Path('feature.txt').write_text('implemented')\n"
            "subprocess.run(['git','add','feature.txt'],check=True)\n"
            "subprocess.run(['git','commit','-m','Implement feature'],check=True)\n"
            "print('private hidden; protected unchanged; committed')\n"
        )

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(self.workspace), *args],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()

        git("init", "-q")
        git("config", "user.name", "Study fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("add", ".")
        git("commit", "-qm", "Starter")
        baseline = git("rev-parse", "HEAD")
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("write"),
                    ev_function_call(
                        "write",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": "python3 probe.py",
                                "yield_time_ms": 10000,
                                "max_output_tokens": 2000,
                            }
                        ),
                    ),
                    ev_completed("write"),
                ]
            )
        )
        self.response("writer done")
        run = self.start(sandbox=SessionSandbox(self.workspace, protected=(assets,)))
        run.bridge.group(
            [{"prompt": "Run the provided compatibility probe.", "writable": True}]
        )
        outputs = [
            item.get("output", "")
            for request in self.mock.requests()
            for item in request.body_json()["input"]
            if item.get("type") == "function_call_output"
        ]
        self.assertIn(
            "private hidden; protected unchanged; committed", "\n".join(outputs)
        )
        self.assertNotEqual(git("rev-parse", "HEAD"), baseline)
        self.assertEqual(git("show", "HEAD:feature.txt"), "implemented")
        self.assertEqual(skill.read_text(), "protected skill")
        self.assertEqual(secret.read_text(), "private-grader-canary-938201")
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("read"),
                    ev_function_call(
                        "read",
                        "exec_command",
                        json.dumps(
                            {
                                "cmd": "python3 -c \"from pathlib import Path; import errno\ntry: Path('feature.txt').write_text('changed')\nexcept OSError as error:\n assert error.errno in (errno.EACCES, errno.EROFS, errno.EPERM); print('REVIEWER_WRITE_DENIED')\"",
                                "yield_time_ms": 1000,
                            }
                        ),
                    ),
                    ev_completed("read"),
                ]
            )
        )
        self.response("reviewer done")
        run.bridge.group([{"prompt": "Attempt the reviewer write probe."}])
        outputs = [
            item.get("output", "")
            for request in self.mock.requests()
            for item in request.body_json()["input"]
            if item.get("type") == "function_call_output"
        ]
        self.assertIn("REVIEWER_WRITE_DENIED", "\n".join(outputs))
        self.assertEqual((self.workspace / "feature.txt").read_text(), "implemented")
        self.assertEqual(run.close()["process"]["stop_status"], "confirmed")
        events = [
            json.loads(line)
            for line in (run.artifacts / "session/invocations.jsonl")
            .read_text()
            .splitlines()
        ]
        self.assertTrue(
            any(
                event.get("type") == "command"
                and "probe.py" in event.get("command", "")
                for event in events
            )
        )
        self.assertTrue(run.result["fidelity"]["complete"])


class HomeSdkIsolationTest(SdkIsolationTest):
    temporary_parent = Path.home() / ".cache"


if __name__ == "__main__":
    unittest.main()
