"""Recipe graph validation and actual control-only planner permissions."""

import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_sdk_workflows import SdkFixture
from app_server_harness import sse, ev_response_created, ev_function_call, ev_completed
from workflows.bmad_orchestrated import BmadOrchestrated, parse_plan
from workflows.filesystem import SessionSandbox


class RecipePlanTest(unittest.TestCase):
    def test_completed_turn_requires_bound_done_spec_before_next_increment(self):
        for state, expected_count, expected_status in (
            ("blocked", 1, "blocked"),
            (None, 1, "unknown"),
            ("done", 2, "completed"),
        ):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace, artifacts = root / "workspace", root / "artifacts"
                folder = workspace / "_bmad-output/specs/spec-probe"
                folder.mkdir(parents=True)
                artifacts.mkdir()
                (folder / "SPEC.md").write_text("# Intent\n")
                (folder / "stories").mkdir()
                install = Mock(
                    workspace=workspace, manifest={"control_paths": ["_bmad-output"]}
                )
                increments = [
                    {
                        "id": name,
                        "intent": "Implement " + name,
                        "acceptance": [name + " works"],
                        "depends_on": [] if name == "one" else ["one"],
                    }
                    for name in ("one", "two")
                ]
                run = Mock(artifacts=artifacts)
                run.session.workspace = str(workspace)
                run.session.turn.side_effect = [
                    {
                        "status": "completed",
                        "text": json.dumps(
                            {
                                "status": "complete",
                                "files": ["_bmad-output/specs/spec-probe/SPEC.md"],
                            }
                        ),
                    },
                    {
                        "status": "completed",
                        "text": json.dumps({"increments": increments}),
                    },
                ]
                called = []

                def invoke(prompt):
                    story = json.loads((folder / "stories.yaml").read_text())[
                        len(called)
                    ]
                    called.append(story["id"])
                    if state:
                        (folder / "stories" / (story["id"] + "-example.md")).write_text(
                            "---\nstatus: " + state + "\n---\n"
                        )
                    return {
                        "turn": {"status": "completed", "text": "done"},
                        "other_spec_claims": [
                            {"status_claim": "done", "path": "unrelated.md"}
                        ],
                    }

                with patch("workflows.bmad_orchestrated.BmadDispatch") as dispatch:
                    dispatch.return_value.invoke.side_effect = invoke
                    result = BmadOrchestrated(run, install).invoke(
                        "Build probe", "probe"
                    )
                self.assertEqual(len(called), expected_count)
                self.assertEqual(result["recipe_status"], expected_status)
                self.assertEqual(result["increments"][0]["story_id"], called[0])
                self.assertEqual(
                    json.loads((artifacts / "orchestrated-result.json").read_text())[
                        "recipe_status"
                    ],
                    expected_status,
                )

    def test_spec_failure_is_persisted_before_propagating(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = Mock(workspace=root)
            run = Mock(artifacts=root)
            run.session.workspace = str(root)
            run.session.turn.side_effect = RuntimeError("spec transport failed")
            with self.assertRaisesRegex(RuntimeError, "spec transport failed"):
                BmadOrchestrated(run, install).invoke("Build probe", "probe")
            result = json.loads((root / "orchestrated-result.json").read_text())
            self.assertEqual(result["recipe_status"], "failed")
            self.assertEqual(result["error"]["type"], "RuntimeError")

    def test_dependencies_cannot_reference_future_or_duplicate_increments(self):
        first = {
            "id": "one",
            "intent": "Implement one",
            "acceptance": ["One works"],
            "depends_on": [],
        }
        second = {
            "id": "two",
            "intent": "Integrate two",
            "acceptance": ["Both work"],
            "depends_on": ["one"],
        }
        self.assertEqual(
            parse_plan(json.dumps({"increments": [first, second]})), [first, second]
        )
        for sequence in (
            [second, first],
            [first, first],
            [{**first, "depends_on": ["one"]}],
            [{**first, "acceptance": []}],
        ):
            with self.assertRaises(ValueError):
                parse_plan(json.dumps({"increments": sequence}))


class PlannerPermissionsTest(SdkFixture):
    def test_planner_writes_only_control_artifacts(self):
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        controls = self.workspace / "_bmad-output"
        protected = self.workspace / "_bmad"
        controls.mkdir()
        protected.mkdir()
        (self.workspace / "product.txt").write_text("starter")
        (protected / "skill.md").write_text("stock")
        for args in (
            ("config", "user.name", "Recipe test"),
            ("config", "user.email", "recipe@example.invalid"),
            ("add", "product.txt"),
            ("commit", "-qm", "Starter"),
        ):
            subprocess.run(["git", "-C", str(self.workspace), *args], check=True)
        baseline = subprocess.check_output(
            ["git", "-C", str(self.workspace), "rev-parse", "HEAD"]
        )
        script = (
            "from pathlib import Path\nimport subprocess\n"
            "for target in ['product.txt','_bmad/skill.md']:\n"
            "    try: Path(target).write_text('tampered')\n"
            "    except OSError: pass\n"
            "    else: raise AssertionError('forbidden write succeeded')\n"
            "commit = subprocess.run(['git','commit','--allow-empty','-m','forbidden'],capture_output=True)\n"
            "assert commit.returncode != 0, 'planner committed product history'\n"
            "Path('_bmad-output/SPEC.md').write_text('spec created')\n"
        )
        self.mock.enqueue_sse(
            sse(
                [
                    ev_response_created("spec"),
                    ev_function_call(
                        "spec",
                        "exec_command",
                        json.dumps({"cmd": "python3 -c " + shlex.quote(script)}),
                    ),
                    ev_completed("spec"),
                ]
            )
        )
        self.response("spec complete")
        run = self.start(
            sandbox=SessionSandbox(
                self.workspace, protected=(protected,), controls=(controls,)
            )
        )
        run.session.new_thread("spec", role="planner")
        run.session.turn("spec", "Run the filesystem probe.")
        self.assertEqual((controls / "SPEC.md").read_text(), "spec created")
        self.assertEqual((self.workspace / "product.txt").read_text(), "starter")
        self.assertEqual((protected / "skill.md").read_text(), "stock")
        self.assertEqual(
            subprocess.check_output(
                ["git", "-C", str(self.workspace), "rev-parse", "HEAD"]
            ),
            baseline,
        )
        self.assertEqual(run.close()["process"]["stop_status"], "confirmed")
