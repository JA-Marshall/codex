"""Synthetic metadata tests; no real held-out content is authored or opened."""

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from corpus_manifest import (
    TARGETS,
    bind_development,
    fingerprint,
    load_index,
    validate_index,
)
from task_registry import discover, inventory, load_task
from task_registry import evaluator_fingerprint
from campaign_inputs import digest
from corpus_calibration import driver_fingerprint


def entry(index, split, track):
    return dict(
        id=f"task-{index}",
        project_id=f"project-{index}",
        lineage_id=f"lineage-{index}",
        duplicate_family=f"family-{index}",
        split=split,
        track=track,
        cohort="primary",
        owner_diagnostic=False,
        content_sha256=fingerprint(["content", index]),
        calibration_sha256=fingerprint(["calibration", index]),
        provenance=dict(
            origin="synthetic",
            origin_fingerprint=fingerprint(["origin", index]),
            revision_fingerprint=fingerprint(["revision", index]),
            exposed_to_tuning=split == "development",
        ),
    )


def complete_index():
    entries = []
    for split, count in TARGETS.items():
        for index in range(count):
            entries.append(
                entry(len(entries), split, "A" if index < count // 2 else "B")
            )
    return dict(
        schema_version=1,
        id="metadata-test",
        state="sealed",
        development_root="development",
        custodian_seal_sha256="a" * 64,
        entries=entries,
    )


class CorpusManifestTest(unittest.TestCase):
    def test_declared_counts_and_independent_confirmation_projects(self):
        data = complete_index()
        result = validate_index(data)
        self.assertEqual(result["primary"]["development"], {"A": 12, "B": 12})
        self.assertEqual(result["declared_projects"]["confirmation"], 24)
        data["entries"][-1]["project_id"] = data["entries"][-2]["project_id"]
        with self.assertRaisesRegex(ValueError, "24 independent"):
            validate_index(data)
        data = complete_index()
        data["entries"].pop()
        with self.assertRaisesRegex(ValueError, "24/12/24"):
            validate_index(data)
        data["state"] = "draft"
        validate_index(data)

    def test_project_lineage_family_origin_and_exact_content_cannot_cross_splits(self):
        for key in [
            "project_id",
            "lineage_id",
            "duplicate_family",
            "content_sha256",
            "origin_fingerprint",
        ]:
            data = complete_index()
            if key == "origin_fingerprint":
                data["entries"][24]["provenance"][key] = data["entries"][0][
                    "provenance"
                ][key]
            else:
                data["entries"][24][key] = data["entries"][0][key]
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "crosses splits"),
            ):
                validate_index(data)

    def test_known_related_and_transitively_related_ids_are_one_independent_unit(self):
        data = complete_index()
        for item in data["entries"][-24:]:
            item["lineage_id"] = "one-lineage"
        with self.assertRaisesRegex(ValueError, "24 independent"):
            validate_index(data)
        data["state"] = "draft"
        self.assertEqual(
            validate_index(data)["declared_ancestry_clusters"]["confirmation"], 1
        )
        data = complete_index()
        data["entries"][-3]["lineage_id"] = data["entries"][-2]["lineage_id"]
        data["entries"][-2]["duplicate_family"] = data["entries"][-1][
            "duplicate_family"
        ]
        with self.assertRaisesRegex(ValueError, "24 independent"):
            validate_index(data)
        data["state"] = "draft"
        self.assertEqual(
            validate_index(data)["declared_ancestry_clusters"]["confirmation"], 22
        )

    def test_diagnostics_do_not_satisfy_primary_track_a_and_exposure_blocks_holdout(
        self,
    ):
        data = complete_index()
        owner = entry(61, "development", "A")
        owner.update(owner_diagnostic=True, cohort="diagnostic")
        data["entries"].append(owner)
        self.assertEqual(validate_index(data)["primary"]["development"]["A"], 12)
        self.assertEqual(validate_index(data)["diagnostics"]["development"], 1)
        owner["cohort"] = "primary"
        with self.assertRaisesRegex(ValueError, "owner diagnostic"):
            validate_index(data)
        data = complete_index()
        data["entries"][24]["provenance"]["exposed_to_tuning"] = True
        with self.assertRaisesRegex(ValueError, "tuning-exposed"):
            validate_index(data)
        data = complete_index()
        data["entries"][24]["brief"] = "Forbidden content in opaque metadata."
        with self.assertRaisesRegex(ValueError, "opaque"):
            validate_index(data)

    def test_development_hash_binding_and_path_alias_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            development = root / "development"
            task_root = development / "task"
            source = (
                Path(__file__).resolve().parents[1]
                / "tasks/sentinels/py-archive-intent"
            )
            shutil.copytree(source, task_root)
            task = load_task(task_root)
            item = entry(0, "development", "A")
            item.update(
                id=task.name,
                project_id=task.manifest["project_id"],
                content_sha256=fingerprint(inventory(task_root)),
            )
            certificate = root / "certificates" / (task.name + ".json")
            certificate.parent.mkdir()
            certificate.write_text(
                json.dumps(
                    dict(
                        schema_version=1,
                        task_id=task.name,
                        **{
                            key: item[key]
                            for key in (
                                "project_id",
                                "lineage_id",
                                "duplicate_family",
                                "content_sha256",
                            )
                        },
                        calibrated=True,
                        model_calls=0,
                        evaluator_sha256=evaluator_fingerprint(),
                        calibration_driver_sha256=driver_fingerprint(),
                        authoring_sha256="a" * 64,
                        calibration_report_sha256="b" * 64,
                        evaluation_sha256={
                            name: "c" * 64
                            for name in [
                                "baseline",
                                "irrelevant-patch",
                                "solution",
                                *task.manifest["mutants"],
                                *task.manifest.get("valid_alternatives", []),
                            ]
                        },
                        limitation="Synthetic metadata fixture, not evidence of corpus completion.",
                    )
                )
            )
            item["calibration_sha256"] = digest(certificate)
            data = complete_index()
            data.update(state="draft", custodian_seal_sha256=None, entries=[item])
            path = root / "corpus.json"
            path.write_text(json.dumps(data))
            bind_development(path, development, {task.name: task})
            with self.assertRaisesRegex(ValueError, "development directory"):
                bind_development(path, root)
            if sys.platform == "linux":
                alias = root / "alias"
                alias.symlink_to(development, target_is_directory=True)
                with self.assertRaises(ValueError):
                    bind_development(path, alias)
                linked_index = root / "linked.json"
                linked_index.symlink_to(path)
                with self.assertRaises(ValueError):
                    load_index(linked_index)
            (task_root / "project/src/app.py").write_text("changed after calibration")
            with self.assertRaisesRegex(ValueError, "content commitment"):
                bind_development(path, development, {task.name: task})

    def test_tuning_discovery_checks_all_metadata_before_hashing_or_loading_packs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, split in [("first", "development"), ("second", "confirmation")]:
                directory = root / name
                directory.mkdir()
                (directory / "manifest.json").write_text(json.dumps({"split": split}))
                (directory / "TASK.md").write_text("content must not be opened")
            with (
                patch("task_registry.sha256") as hashed,
                patch("task_registry.load_task") as loaded,
            ):
                with self.assertRaisesRegex(ValueError, "forbidden held-out"):
                    discover(root, allowed_splits={"development"})
                hashed.assert_not_called()
                loaded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
