mod common;
mod support;

use std::panic::AssertUnwindSafe;

use codex_lab::ActionKind;
use codex_lab::ApprovalTarget;
use codex_lab::LabError;
use codex_lab::LabRun;
use codex_lab::StepProgress;
use codex_lab::StepStatus;
use codex_lab::VerificationEvidence;
use codex_lab::WorkflowState;
use pretty_assertions::assert_eq;

fn approve(run: &mut LabRun) -> codex_lab::Result<ApprovalTarget> {
    run.begin_planning()?;
    run.submit_plan(common::sample_plan())?;
    let target = run
        .snapshot()
        .target
        .clone()
        .ok_or_else(|| LabError::Invalid("fixture plan has no approval target".into()))?;
    run.approve(target.clone(), "human-reviewer")?;
    Ok(target)
}

fn assert_denied(run: &mut LabRun, target: &ApprovalTarget) {
    let before = run.snapshot().clone();
    let mut calls = 0;
    for kind in [ActionKind::Implementation, ActionKind::Verification] {
        assert!(
            run.perform(target, kind, || {
                calls += 1;
                Ok(())
            })
            .is_err()
        );
    }
    assert_eq!(calls, 0);
    assert_eq!(run.snapshot(), &before);
}

#[test]
fn every_preapproval_phase_denies_actions_and_target_possession_is_not_authority() {
    let (_root, mut run) = support::new_run().unwrap();
    let forged = ApprovalTarget {
        run_id: "run".into(),
        plan_id: "fixture-plan".into(),
        revision: 1,
        content_sha256: common::sample_plan().digest().unwrap(),
        run_spec_sha256: "0".repeat(64),
    };
    assert_eq!(run.snapshot().state, WorkflowState::Researching);
    assert_denied(&mut run, &forged);
    assert!(run.approve(forged.clone(), "human").is_err());
    assert!(run.submit_plan(common::sample_plan()).is_err());
    run.begin_planning().unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::Planning);
    assert_denied(&mut run, &forged);
    assert!(run.begin_verification().is_err());
    run.submit_plan(common::sample_plan()).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::AwaitingPlanApproval);
    assert_denied(&mut run, &target);
    assert!(run.complete().is_err());
    assert!(run.approve(target.clone(), " ").is_err());
    run.approve(target.clone(), "human").unwrap();
    assert_eq!(
        run.perform(&target, ActionKind::Implementation, || Ok(42))
            .unwrap(),
        42
    );
}

#[test]
fn approval_and_action_admission_bind_every_target_dimension() {
    let (_root, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(common::sample_plan()).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    let mismatches = [
        ApprovalTarget {
            run_id: "another-run".into(),
            ..target.clone()
        },
        ApprovalTarget {
            plan_id: "another-plan".into(),
            ..target.clone()
        },
        ApprovalTarget {
            revision: 2,
            ..target.clone()
        },
        ApprovalTarget {
            content_sha256: "0".repeat(64),
            ..target.clone()
        },
        ApprovalTarget {
            run_spec_sha256: "0".repeat(64),
            ..target.clone()
        },
    ];
    for mismatch in &mismatches {
        assert!(run.approve(mismatch.clone(), "human").is_err());
        assert_denied(&mut run, mismatch);
    }
    run.approve(target, "human").unwrap();
    for mismatch in &mismatches {
        assert_denied(&mut run, mismatch);
    }
}

#[test]
fn human_edits_and_rejection_require_a_new_reviewed_revision() {
    let (_root, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    let mut plan = common::sample_plan();
    run.submit_plan(plan.clone()).unwrap();
    let original = run.snapshot().target.clone().unwrap();
    assert!(
        run.edit_plan(plan.clone(), "human", "Clarify acceptance")
            .is_err()
    );
    plan.revision = 2;
    plan.assumptions.push("Preserve existing callers".into());
    run.edit_plan(plan.clone(), "human", "Clarify acceptance")
        .unwrap();
    let edited = run.snapshot().target.clone().unwrap();
    assert!(run.approve(original.clone(), "human").is_err());
    assert_denied(&mut run, &original);
    assert_denied(&mut run, &edited);
    run.reject(edited.clone(), "human", "Needs narrower scope")
        .unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::Planning);
    assert!(run.approve(edited.clone(), "human").is_err());
    assert_denied(&mut run, &edited);
    plan.revision = 3;
    run.submit_plan(plan.clone()).unwrap();
    run.approve(run.snapshot().target.clone().unwrap(), "human")
        .unwrap();
    assert_eq!(run.plan(), Some(&plan));
}

#[test]
fn amendment_revokes_admission_and_requires_a_new_plan_and_human_decision() {
    let (_root, mut run) = support::new_run().unwrap();
    let original = approve(&mut run).unwrap();
    run.record_step(
        "S01",
        StepProgress {
            status: StepStatus::Completed,
            evidence: Some("implementation-evidence".into()),
        },
    )
    .unwrap();
    run.request_amendment("The parser has an undocumented caller")
        .unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::AwaitingPlanAmendment);
    assert_eq!(
        (&run.snapshot().target, &run.snapshot().approved),
        (&None, &None)
    );
    assert_denied(&mut run, &original);
    assert!(run.approve(original.clone(), "human").is_err());
    assert!(run.submit_plan(common::sample_plan()).is_err());
    let mut plan = common::sample_plan();
    plan.revision = 2;
    plan.discoveries.push("Undocumented caller found".into());
    run.submit_plan(plan).unwrap();
    let amended = run.snapshot().target.clone().unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::AwaitingPlanAmendment);
    assert!(
        run.snapshot()
            .progress
            .values()
            .all(|p| p.status == StepStatus::Pending)
    );
    assert_denied(&mut run, &amended);
    run.reject(amended.clone(), "human", "Review further")
        .unwrap();
    assert_eq!(run.snapshot().state, WorkflowState::AwaitingPlanAmendment);
    assert_denied(&mut run, &amended);
    run.approve(amended.clone(), "human").unwrap();
    assert_denied(&mut run, &original);
    assert_eq!(
        run.perform(&amended, ActionKind::Implementation, || Ok("approved"))
            .unwrap(),
        "approved"
    );
}

#[test]
fn retired_step_ids_cannot_be_reintroduced_and_blockers_prevent_approval() {
    let (_root, mut run) = support::new_run().unwrap();
    run.begin_planning().unwrap();
    let mut plan = common::sample_plan();
    plan.blockers.push("Missing API contract".into());
    run.submit_plan(plan).unwrap();
    let blocked = run.snapshot().target.clone().unwrap();
    assert!(run.approve(blocked.clone(), "human").is_err());
    assert_denied(&mut run, &blocked);
    let mut revision = common::sample_plan();
    revision.revision = 2;
    revision.steps.pop();
    run.edit_plan(revision, "human", "Narrow scope and resolve blocker")
        .unwrap();
    let before = run.snapshot().clone();
    let mut reused = common::sample_plan();
    reused.revision = 3;
    assert!(
        run.edit_plan(reused, "human", "Reuse retired step")
            .is_err()
    );
    assert_eq!(run.snapshot(), &before);
}

#[test]
fn dependencies_progress_and_verification_control_completion() {
    let (_root, mut run) = support::new_run().unwrap();
    let target = approve(&mut run).unwrap();
    let plan = run.plan().cloned();
    let completed = StepProgress {
        status: StepStatus::Completed,
        evidence: Some("step-evidence".into()),
    };
    assert!(run.begin_verification().is_err());
    assert!(run.record_step("S02", completed.clone()).is_err());
    assert!(run.record_step("unknown", completed.clone()).is_err());
    assert!(
        run.record_step(
            "S01",
            StepProgress {
                status: StepStatus::Completed,
                evidence: None
            }
        )
        .is_err()
    );
    run.record_step(
        "S01",
        StepProgress {
            status: StepStatus::InProgress,
            evidence: None,
        },
    )
    .unwrap();
    assert!(
        run.record_step(
            "S01",
            StepProgress {
                status: StepStatus::Pending,
                evidence: None
            }
        )
        .is_err()
    );
    run.record_step("S01", completed.clone()).unwrap();
    assert!(run.record_step("S01", completed.clone()).is_err());
    run.record_step("S02", completed).unwrap();
    assert_eq!(
        (run.plan(), &run.snapshot().approved),
        (plan.as_ref(), &Some(target.clone()))
    );
    run.begin_verification().unwrap();
    let mut calls = 0;
    assert!(
        run.perform(&target, ActionKind::Implementation, || {
            calls += 1;
            Ok(())
        })
        .is_err()
    );
    run.perform(&target, ActionKind::Verification, || {
        calls += 1;
        Ok(())
    })
    .unwrap();
    assert_eq!(calls, 1);
    assert!(run.complete().is_err());
    let mut evidence = VerificationEvidence {
        passed: false,
        reference: "test-result".into(),
        acceptance_criteria: vec!["AC01".into()],
    };
    assert!(
        run.record_verification("unknown", evidence.clone())
            .is_err()
    );
    let mut invalid = evidence.clone();
    invalid.acceptance_criteria = vec!["unknown".into()];
    assert!(run.record_verification("V01", invalid).is_err());
    run.record_verification("V01", evidence.clone()).unwrap();
    assert!(run.complete().is_err());
    evidence.passed = true;
    evidence.acceptance_criteria.clear();
    run.record_verification("V01", evidence.clone()).unwrap();
    assert!(run.complete().is_err());
    evidence.acceptance_criteria.push("AC01".into());
    run.record_verification("V01", evidence).unwrap();
    let mut expected = run.snapshot().clone();
    expected.state = WorkflowState::Completed;
    expected.approved = None;
    run.complete().unwrap();
    assert_eq!(run.snapshot(), &expected);
    assert_denied(&mut run, &target);
    assert!(run.fail("Cannot reopen completed run").is_err());
    assert!(run.begin_planning().is_err());
    assert!(run.approve(target, "human").is_err());
}

#[test]
fn host_action_errors_and_panics_revoke_authority() {
    let (_root, mut run) = support::new_run().unwrap();
    let target = approve(&mut run).unwrap();
    let result: codex_lab::Result<()> = run.perform(&target, ActionKind::Implementation, || {
        Err(LabError::Invalid("simulated action failure".into()))
    });
    assert!(result.is_err());
    assert_eq!(run.snapshot().state, WorkflowState::Failed);
    assert_eq!(run.snapshot().approved, None);
    assert_denied(&mut run, &target);
    assert!(run.approve(target, "human").is_err());

    let (_other_root, mut panicking) = support::new_run().unwrap();
    let target = approve(&mut panicking).unwrap();
    let outcome = std::panic::catch_unwind(AssertUnwindSafe(|| {
        panicking.perform(
            &target,
            ActionKind::Implementation,
            || -> codex_lab::Result<()> {
                panic!("simulated host panic");
            },
        )
    }));
    assert!(outcome.is_err());
    assert_eq!(panicking.snapshot().state, WorkflowState::Failed);
    assert_eq!(panicking.snapshot().approved, None);
    assert_denied(&mut panicking, &target);
}
