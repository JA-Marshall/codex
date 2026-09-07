use super::*;
use pretty_assertions::assert_eq;

#[test]
fn delegated_decisions_require_opt_in_and_reauthorize_exact_amended_targets() {
    let (_manual_root, mut manual) = support::new_run().unwrap();
    manual.begin_planning().unwrap();
    manual.submit_plan(common::sample_plan()).unwrap();
    let manual_target = manual.snapshot().target.clone().unwrap();
    let policy_digest = "a".repeat(64);
    assert!(
        manual
            .approve_delegated(manual_target.clone(), &policy_digest)
            .is_err()
    );
    assert_denied(&mut manual, &manual_target);

    let root = tempfile::tempdir().unwrap();
    let spec = support::run_spec_with_policy(
        root.path(),
        codex_lab::Renderer::Markdown,
        0,
        "campaign_delegated",
    )
    .unwrap();
    let mut run = LabRun::create(root.path(), "delegated", spec).unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(common::sample_plan()).unwrap();
    let original = run.snapshot().target.clone().unwrap();
    assert!(
        run.approve_delegated(original.clone(), "not-a-digest")
            .is_err()
    );
    assert!(
        run.approve_delegated(manual_target, &policy_digest)
            .is_err()
    );
    assert_denied(&mut run, &original);
    run.approve_delegated(original.clone(), &policy_digest)
        .unwrap();
    run.perform(&original, ActionKind::Implementation, || Ok(()))
        .unwrap();

    run.request_amendment("new information").unwrap();
    assert_denied(&mut run, &original);
    let mut plan = common::sample_plan();
    plan.revision = 2;
    plan.goal.push_str(" with the discovered boundary covered");
    run.submit_plan(plan).unwrap();
    let amended = run.snapshot().target.clone().unwrap();
    assert!(run.approve_delegated(original, &policy_digest).is_err());
    assert_denied(&mut run, &amended);
    run.approve_delegated(amended.clone(), &policy_digest)
        .unwrap();
    run.perform(&amended, ActionKind::Implementation, || Ok(()))
        .unwrap();

    let decisions: Vec<serde_json::Value> = std::fs::read_dir(run.artifacts().join("decisions"))
        .unwrap()
        .map(|entry| {
            serde_json::from_slice(&std::fs::read(entry.unwrap().path()).unwrap()).unwrap()
        })
        .collect();
    assert_eq!(decisions.len(), 2);
    for decision in decisions {
        assert_eq!(decision["type"], "delegated_approved");
        assert_eq!(decision["policy_sha256"], policy_digest);
        assert_eq!(decision["target"]["run_id"], "delegated");
    }
}

#[test]
fn delegated_decision_recording_failure_never_releases_authority() {
    let root = tempfile::tempdir().unwrap();
    let spec = support::run_spec_with_policy(
        root.path(),
        codex_lab::Renderer::Markdown,
        0,
        "campaign_delegated",
    )
    .unwrap();
    let mut run = LabRun::create(root.path(), "delegated", spec).unwrap();
    run.begin_planning().unwrap();
    run.submit_plan(common::sample_plan()).unwrap();
    let target = run.snapshot().target.clone().unwrap();
    std::fs::write(
        run.artifacts().join("decisions/4.json"),
        b"existing observation",
    )
    .unwrap();
    assert!(
        run.approve_delegated(target.clone(), &"a".repeat(64))
            .is_err()
    );
    assert_eq!(run.snapshot().state, WorkflowState::Failed);
    assert_denied(&mut run, &target);
}
