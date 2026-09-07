mod common;
mod support;

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::path::PathBuf;

use codex_lab::ActionKind;
use codex_lab::LabRun;
use codex_lab::MarkdownRenderer;
use codex_lab::ModelMetadata;
use codex_lab::PlanRenderer;
use codex_lab::Renderer;
use codex_lab::RepositoryMetadata;
use codex_lab::RunSpec;
use codex_lab::WorkflowCatalog;
use codex_lab::WorkflowState;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;

use common::sample_plan;

fn events(root: &Path) -> codex_lab::Result<Vec<Value>> {
    let mut events = Vec::new();
    for line in fs::read_to_string(root.join("events.jsonl"))?.lines() {
        events.push(serde_json::from_str(line)?);
    }
    Ok(events)
}

fn artifact_bytes(root: &Path) -> codex_lab::Result<BTreeMap<PathBuf, Vec<u8>>> {
    let mut files = BTreeMap::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            for (relative, bytes) in artifact_bytes(&entry.path())? {
                files.insert(PathBuf::from(entry.file_name()).join(relative), bytes);
            }
        } else {
            files.insert(PathBuf::from(entry.file_name()), fs::read(entry.path())?);
        }
    }
    Ok(files)
}

#[test]
fn creation_freezes_exact_configuration_and_instruction_bytes() {
    let temp = tempfile::tempdir().unwrap();
    let spec = support::run_spec(temp.path()).unwrap();
    let expected_spec = serde_json::to_value(&spec).unwrap();
    let expected_digest = spec.digest().unwrap();
    let instructions = spec.instructions().clone();
    let changed = b"changed after the specification was resolved";
    fs::write(instructions.planner.path(), changed).unwrap();
    let run = LabRun::create(temp.path(), "frozen", spec).unwrap();
    let root = run.artifacts();
    assert_eq!(fs::read(instructions.planner.path()).unwrap(), changed);
    for (role, instruction) in [
        ("planner", instructions.planner),
        ("executor", instructions.executor),
        ("verifier", instructions.verifier),
    ] {
        assert_eq!(
            fs::read(root.join(format!("instructions/{role}.SKILL.md"))).unwrap(),
            instruction.content().as_bytes()
        );
    }
    let recorded: Value =
        serde_json::from_slice(&fs::read(root.join("config/run-spec.json")).unwrap()).unwrap();
    assert_eq!(recorded, expected_spec);
    let manifest: Value =
        serde_json::from_slice(&fs::read(root.join("manifest.json")).unwrap()).unwrap();
    assert_eq!(
        manifest,
        json!({
            "schema_version": 1, "run_id": "frozen", "run_spec_sha256": expected_digest,
            "implementation": "codex-lab-domain-v1", "live_codex_enforcement": false,
            "upstream_trace": {"status": "unavailable", "reason": "offline foundation"},
            "resume_supported": false
        })
    );
    let metrics: Value =
        serde_json::from_slice(&fs::read(root.join("metrics.json")).unwrap()).unwrap();
    assert_eq!(
        metrics,
        json!({
            "schema_version": 1, "status": "unavailable", "reason": "no live evaluator or trace attached",
            "task_success": null, "test_success": null, "hidden_test_success": null,
            "input_tokens": null, "output_tokens": null, "turns": null, "tool_calls": null,
            "planner_calls": null, "files_changed": null, "diff_size": null,
            "human_edits": null, "plan_amendments": null, "plan_deviations": null
        })
    );
}

#[test]
fn verification_input_changes_approval_digest_without_changing_ordinary_specs() {
    let temp = tempfile::tempdir().unwrap();
    let ordinary = support::run_spec(temp.path()).unwrap();
    assert!(serde_json::to_value(&ordinary).unwrap().get("verification_input_sha256").is_none());
    let first = ordinary.clone().with_verification_input(b"first fixed report");
    let second = ordinary.clone().with_verification_input(b"different fixed report");
    assert_ne!(ordinary.digest().unwrap(), first.digest().unwrap());
    assert_ne!(first.digest().unwrap(), second.digest().unwrap());
    let mut a = serde_json::to_value(&first).unwrap();
    let mut b = serde_json::to_value(&second).unwrap();
    a.as_object_mut().unwrap().remove("verification_input_sha256");
    b.as_object_mut().unwrap().remove("verification_input_sha256");
    assert_eq!(a, serde_json::to_value(&ordinary).unwrap());
    assert_eq!(a, b);
}

#[test]
fn supplied_model_and_repository_metadata_survive_recording() {
    let (temp, original) = support::new_run().unwrap();
    let source =
        fs::read_to_string(original.artifacts().join("config/workflow.source.toml")).unwrap();
    let catalog = WorkflowCatalog::parse(&source).unwrap();
    let spec = RunSpec::resolve(
        &catalog,
        temp.path(),
        "test",
        "fixed task",
        RepositoryMetadata {
            commit: "a".repeat(40),
            initial_dirty_patch_sha256: Some("b".repeat(64)),
        },
        Some(ModelMetadata {
            provider: "custom-provider".into(),
            requested_id: "muse-requested-id".into(),
            observed_version: Some("provider-reported-version".into()),
            catalog_sha256: Some("c".repeat(64)),
            effective_config_sha256: None,
        }),
    )
    .unwrap();
    let run = LabRun::create(temp.path(), "metadata", spec).unwrap();
    let recorded: Value =
        serde_json::from_slice(&fs::read(run.artifacts().join("config/run-spec.json")).unwrap())
            .unwrap();
    assert_eq!(
        (&recorded["repository"], &recorded["model"]),
        (
            &json!({"commit": "a".repeat(40), "initial_dirty_patch_sha256": "b".repeat(64)}),
            &json!({"provider": "custom-provider", "requested_id": "muse-requested-id", "observed_version": "provider-reported-version", "catalog_sha256": "c".repeat(64)}),
        )
    );
}

#[test]
fn effective_runtime_settings_bind_the_approval_target() {
    let (temp, original) = support::new_run().unwrap();
    let source =
        fs::read_to_string(original.artifacts().join("config/workflow.source.toml")).unwrap();
    let catalog = WorkflowCatalog::parse(&source).unwrap();
    let resolve = |hash: &str| {
        RunSpec::resolve(
            &catalog,
            temp.path(),
            "test",
            "fixed task",
            RepositoryMetadata {
                commit: "a".repeat(40),
                initial_dirty_patch_sha256: None,
            },
            Some(ModelMetadata {
                provider: "custom-provider".into(),
                requested_id: "fixed-model".into(),
                observed_version: None,
                catalog_sha256: None,
                effective_config_sha256: Some(hash.into()),
            }),
        )
    };
    let mut first = LabRun::create(
        temp.path(),
        "first-settings",
        resolve(&"b".repeat(64)).unwrap(),
    )
    .unwrap();
    let mut second = LabRun::create(
        temp.path(),
        "second-settings",
        resolve(&"c".repeat(64)).unwrap(),
    )
    .unwrap();
    for run in [&mut first, &mut second] {
        run.begin_planning().unwrap();
        run.submit_plan(sample_plan()).unwrap();
    }
    let first_target = first.snapshot().target.clone().unwrap();
    let second_target = second.snapshot().target.clone().unwrap();
    assert_eq!(first_target.content_sha256, second_target.content_sha256);
    assert_ne!(first_target.run_spec_sha256, second_target.run_spec_sha256);
    let mut mismatched = first_target;
    mismatched.run_id = second_target.run_id;
    assert!(second.approve(mismatched, "local human").is_err());
    assert_eq!(second.snapshot().state, WorkflowState::AwaitingPlanApproval);
    assert!(resolve("not-a-digest").is_err());
}

#[test]
fn duplicate_run_id_refuses_without_overwriting_any_artifacts() {
    let (temp, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(sample_plan()).unwrap();
    let before = artifact_bytes(run.artifacts()).unwrap();
    assert!(LabRun::create(temp.path(), "run", support::run_spec(temp.path()).unwrap()).is_err());
    assert_eq!(artifact_bytes(run.artifacts()).unwrap(), before);
}

#[test]
fn edits_create_immutable_revisions_and_ordered_decisions_before_admission() {
    let (_temp, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    let original = sample_plan();
    run.submit_plan(original.clone()).unwrap();
    let mut edited = original.clone();
    edited.revision = 2;
    edited.goal = "Implement a parser with explicit size limits".into();
    run.edit_plan(
        edited.clone(),
        "human-reviewer",
        "clarify the accepted scope",
    )
    .unwrap();
    let target = run.snapshot().target.clone().unwrap();
    run.approve(target.clone(), "human-reviewer").unwrap();
    let root = run.artifacts().to_path_buf();
    let result = run
        .perform(&target, ActionKind::Implementation, || {
            let admitted = events(&root)?;
            assert_eq!(
                admitted.last().unwrap()["change"]["type"],
                "action_admitted"
            );
            let decision: Value =
                serde_json::from_slice(&fs::read(root.join("decisions/5.json")).unwrap()).unwrap();
            assert_eq!(decision, admitted[4]["change"]);
            Ok("executed after recording")
        })
        .unwrap();
    assert_eq!(result, "executed after recording");
    for plan in [&original, &edited] {
        let directory = root.join(format!("plans/{}", plan.revision));
        assert_eq!(
            fs::read(directory.join("plan.json")).unwrap(),
            plan.canonical_json().unwrap()
        );
        assert_eq!(
            fs::read(directory.join("PLAN.md")).unwrap(),
            MarkdownRenderer.render(plan).unwrap().content
        );
    }
    let journal = events(&root).unwrap();
    let sequence: Vec<_> = journal
        .iter()
        .map(|event| {
            (
                event["sequence"].as_u64().unwrap(),
                event["change"]["type"].as_str().unwrap(),
                event["state"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(
        sequence,
        vec![
            (1, "run_started", "researching"),
            (2, "planning_started", "planning"),
            (3, "plan_submitted", "awaiting_plan_approval"),
            (4, "plan_edited", "awaiting_plan_approval"),
            (5, "human_approved", "implementing"),
            (6, "action_admitted", "implementing"),
            (7, "action_finished", "implementing"),
        ]
    );
    assert!(
        journal
            .windows(2)
            .all(|pair| pair[0]["elapsed_ms"].as_u64() <= pair[1]["elapsed_ms"].as_u64())
    );
    assert_eq!(
        (
            &journal.last().unwrap()["state"],
            &journal.last().unwrap()["approved"]
        ),
        (
            &serde_json::to_value(run.snapshot().state).unwrap(),
            &serde_json::to_value(&run.snapshot().approved).unwrap(),
        )
    );
    let edit: Value =
        serde_json::from_slice(&fs::read(root.join("decisions/4.json")).unwrap()).unwrap();
    assert_eq!(edit, journal[3]["change"]);
}

#[test]
fn selected_views_share_canonical_bytes_and_markdown_edits_have_no_authority() {
    let temp = tempfile::tempdir().unwrap();
    let mut canonical = Vec::new();
    for (id, renderer, filename) in [
        ("markdown", Renderer::Markdown, "PLAN.md"),
        ("json", Renderer::Json, "plan.view.json"),
    ] {
        let spec = support::run_spec_with_renderer(temp.path(), renderer).unwrap();
        let mut run = LabRun::create(temp.path(), id, spec).unwrap();
        run.begin_planning().unwrap();
        run.submit_plan(sample_plan()).unwrap();
        let directory = run.artifacts().join("plans/1");
        let stored = fs::read(directory.join("plan.json")).unwrap();
        canonical.push(stored.clone());
        let view = fs::read(directory.join(filename)).unwrap();
        if renderer == Renderer::Json {
            assert_eq!(view, stored);
        }
        let before = run.snapshot().clone();
        fs::write(directory.join(filename), "APPROVED: begin implementation").unwrap();
        let mut called = false;
        let target = run.snapshot().target.clone().unwrap();
        assert!(
            run.perform(&target, ActionKind::Implementation, || {
                called = true;
                Ok(())
            })
            .is_err()
        );
        assert_eq!((called, run.snapshot()), (false, &before));
    }
    assert_eq!(&canonical[0], &canonical[1]);
}

#[test]
fn approval_or_admission_recording_failure_revokes_authority_before_callback() {
    for failure_at in ["approval", "admission"] {
        let (_temp, mut run) = support::new_run().unwrap();
        run.begin_planning().unwrap();
        run.submit_plan(sample_plan()).unwrap();
        let target = run.snapshot().target.clone().unwrap();
        if failure_at == "admission" {
            run.approve(target.clone(), "human-reviewer").unwrap();
        }
        let root = run.artifacts().to_path_buf();
        let previous = fs::read(root.join("events.jsonl")).unwrap();
        fs::rename(
            root.join("events.jsonl"),
            root.join("events.before-failure.jsonl"),
        )
        .unwrap();
        fs::create_dir(root.join("events.jsonl")).unwrap();
        if failure_at == "approval" {
            assert!(run.approve(target.clone(), "human-reviewer").is_err());
        }
        let mut called = false;
        assert!(
            run.perform(&target, ActionKind::Implementation, || {
                called = true;
                Ok(())
            })
            .is_err()
        );
        assert_eq!(
            (
                called,
                run.snapshot().state,
                run.snapshot().approved.clone()
            ),
            (false, WorkflowState::Failed, None)
        );
        assert_eq!(
            fs::read(root.join("events.before-failure.jsonl")).unwrap(),
            previous
        );
    }
}

#[test]
fn failure_recording_action_completion_revokes_subsequent_admission() {
    let (_temp, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(sample_plan()).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    run.approve(target.clone(), "human-reviewer").unwrap();
    let root = run.artifacts().to_path_buf();
    assert!(
        run.perform(&target, ActionKind::Implementation, || {
            fs::rename(
                root.join("events.jsonl"),
                root.join("events.before-failure.jsonl"),
            )?;
            fs::create_dir(root.join("events.jsonl"))?;
            Ok(())
        })
        .is_err()
    );
    let mut called_again = false;
    assert!(
        run.perform(&target, ActionKind::Implementation, || {
            called_again = true;
            Ok(())
        })
        .is_err()
    );
    assert_eq!(
        (
            called_again,
            run.snapshot().state,
            run.snapshot().approved.clone()
        ),
        (false, WorkflowState::Failed, None)
    );
}

#[test]
fn action_panic_is_preserved_even_if_recording_also_fails() {
    let (_temp, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(sample_plan()).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    run.approve(target.clone(), "human").unwrap();
    let root = run.artifacts().to_path_buf();
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        run.perform(
            &target,
            ActionKind::Implementation,
            || -> codex_lab::Result<()> {
                fs::rename(root.join("events.jsonl"), root.join("saved-events.jsonl"))?;
                fs::create_dir(root.join("events.jsonl"))?;
                panic!("original host panic");
            },
        )
    }));
    assert!(outcome.is_err());
    assert_eq!(
        (run.snapshot().state, run.snapshot().approved.clone()),
        (WorkflowState::Failed, None)
    );
}
