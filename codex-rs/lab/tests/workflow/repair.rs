use super::*;
use pretty_assertions::assert_eq;

#[test]
fn repairs_require_failure_preserve_approval_and_never_reset_budget_on_amendment() {
    let root = tempfile::tempdir().unwrap();
    let spec =
        support::run_spec_with_repairs(root.path(), codex_lab::Renderer::Markdown, 1).unwrap();
    let mut run = LabRun::create(root.path(), "repair", spec).unwrap();
    assert!(run.begin_repair().is_err());
    let approved = approve(&mut run).unwrap();
    assert!(run.begin_repair().is_err());
    for id in ["S01", "S02"] {
        run.record_step(
            id,
            StepProgress {
                status: StepStatus::Completed,
                evidence: Some("implementation".into()),
            },
        )
        .unwrap();
    }
    run.begin_verification().unwrap();
    assert!(run.begin_repair().is_err());
    run.record_verification(
        "V01",
        VerificationEvidence {
            passed: false,
            reference: "failed-command".into(),
            acceptance_criteria: vec!["AC01".into()],
        },
    )
    .unwrap();
    run.begin_repair().unwrap();
    assert_eq!(run.snapshot().approved, Some(approved));
    assert!(run.snapshot().verification.is_empty());
    assert!(
        run.snapshot()
            .progress
            .values()
            .all(|p| p.status == StepStatus::Pending)
    );
    assert!(run.begin_verification().is_err());
    run.request_amendment("new discovery").unwrap();
    assert!(run.begin_repair().is_err());
    let mut amended = common::sample_plan();
    amended.revision = 2;
    run.submit_plan(amended).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    run.approve(target, "human").unwrap();
    for id in ["S01", "S02"] {
        run.record_step(
            id,
            StepProgress {
                status: StepStatus::Completed,
                evidence: Some("implementation".into()),
            },
        )
        .unwrap();
    }
    run.begin_verification().unwrap();
    run.record_verification(
        "V01",
        VerificationEvidence {
            passed: false,
            reference: "still-failed".into(),
            acceptance_criteria: vec!["AC01".into()],
        },
    )
    .unwrap();
    assert!(run.begin_repair().is_err());
    assert!(run.complete().is_err());
}
