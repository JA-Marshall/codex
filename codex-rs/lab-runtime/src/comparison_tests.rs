use std::fs;

use anyhow::Result;
use pretty_assertions::assert_eq;

use super::*;
use crate::EvidenceStore;
use crate::RunAuthority;
use crate::authority_support;

fn observation(renderer: &str) -> Observation {
    Observation {
        controls: json!({"plan":{"renderer":renderer,"canonical_sha256":"same"},
        "task":"same","repository":{"commit":"same"},"model":{"id":"fixed"},
        "roles":{"planner":"same","executor":"same","verifier":"same"},
        "settings":{"context_window":8192,"catalog":"same","binary":"same","permissions":"same"},
        "evaluator":{"sha256":"same"}}),
        metadata: json!({"run":renderer}),
        outcomes: json!({"task_success":true}),
        problems: Vec::new(),
    }
}

#[test]
fn comparison_varies_only_renderer_and_reports_metadata_separately() {
    let left = observation("markdown");
    let right = observation("json");
    let report = report(&left, &right, "plan.renderer");
    assert_eq!(report["classification"], "controlled_recorded_pair");
    assert_eq!(
        report["control_differences"],
        json!([{"path":"plan.renderer","left":"markdown","right":"json"}])
    );
    assert_eq!(
        report["metadata_differences"],
        json!([{"path":"run","left":"markdown","right":"json"}])
    );
    assert_eq!(report["immutable_serving_revision_established"], false);
}

#[test]
fn comparison_rejects_every_unrelated_control_change_missing_control_and_incomplete_run() {
    let left = observation("markdown");
    for pointer in [
        "/plan/canonical_sha256",
        "/task",
        "/repository/commit",
        "/model/id",
        "/roles/planner",
        "/roles/executor",
        "/roles/verifier",
        "/settings/context_window",
        "/settings/catalog",
        "/settings/binary",
        "/settings/permissions",
        "/evaluator/sha256",
    ] {
        let mut right = observation("json");
        *right.controls.pointer_mut(pointer).unwrap() = json!("changed");
        let report = report(&left, &right, "plan.renderer");
        assert_eq!(report["classification"], "descriptive_only", "{pointer}");
        assert_eq!(report["control_differences"].as_array().unwrap().len(), 2);
    }
    let mut right = observation("json");
    right.controls["unknown_setting"] = Value::Null;
    assert_eq!(
        report(&left, &right, "plan.renderer")["classification"],
        "descriptive_only"
    );
    for problem in [
        "missing evaluator",
        "amended plan",
        "incomplete run",
        "invalid lineage",
    ] {
        let mut right = observation("json");
        right.problems.push(problem.into());
        assert_eq!(
            report(&left, &right, "plan.renderer")["classification"],
            "descriptive_only"
        );
    }
    assert_eq!(
        report(&left, &left, "plan.renderer")["classification"],
        "descriptive_only"
    );
}

#[test]
fn comparison_reads_pending_runs_without_modifying_them_and_refuses_output_overlap() -> Result<()> {
    let (left_root, mut left_run) = authority_support::new_run()?;
    let (right_root, mut right_run) = authority_support::new_run()?;
    for run in [&mut left_run, &mut right_run] {
        run.begin_planning()?;
        run.submit_plan(authority_support::plan(1)?)?;
    }
    let left_authority = RunAuthority::new(left_run)?;
    let right_authority = RunAuthority::new(right_run)?;
    for authority in [&left_authority, &right_authority] {
        let store = EvidenceStore::new(authority.artifacts()?)?;
        store.write_json("effective-settings.json", &json!({"schema_version":1}))?;
    }
    let left = left_root.path().join("run");
    let right = right_root.path().join("run");
    let before = fs::read(left.join("events.jsonl"))?;
    assert!(compare_runs(&left, &right, "plan.renderer", &left.join("report")).is_err());
    let report_path = compare_runs(
        &left,
        &right,
        "plan.renderer",
        &left_root.path().join("report"),
    )?;
    let report: Value = serde_json::from_slice(&fs::read(report_path)?)?;
    assert_eq!(report["classification"], "descriptive_only");
    assert!(
        report["left"]["problems"]
            .as_array()
            .unwrap()
            .iter()
            .any(|value| value == "workflow did not complete")
    );
    assert_eq!(fs::read(left.join("events.jsonl"))?, before);
    assert!(compare_runs(&left, &right, "model", &left_root.path().join("another")).is_err());
    Ok(())
}
