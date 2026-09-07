#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use std::fs;

use anyhow::Result;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use codex_lab::WorkflowState;
use codex_lab_runtime::HumanDecision;
use codex_lab_runtime::HumanReviewer;
use codex_lab_runtime::prepare_run;
use codex_lab_runtime::run_prepared;
use core_test_support::responses;
use pretty_assertions::assert_eq;
use serde_json::Value;
use wiremock::MockServer;

struct Decline {
    targets: Vec<ApprovalTarget>,
}

impl HumanReviewer for Decline {
    fn review(&mut self, target: &ApprovalTarget, _rendered: &RenderedPlan) -> Result<HumanDecision> {
        self.targets.push(target.clone());
        Ok(HumanDecision::Abort)
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn prepared_generated_plan_shuts_down_then_child_requires_a_new_decision() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let plan = support::plan(1)?;
    let sequence = [
        ("research", "README.md describes the greeting fixture.".into()),
        ("planning", serde_json::to_string(&plan)?),
    ].into_iter().map(|(id, text)| responses::sse(vec![
        responses::ev_response_created(id),
        responses::ev_assistant_message(id, &text),
        responses::ev_completed_with_tokens(id, 7),
    ])).collect();
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let prepared = prepare_run(fixture.options("prepared", "md", None), fixture.paths.clone()).await?;
    assert_eq!((prepared.state, prepared.phase_threads), (WorkflowState::AwaitingPlanApproval, 2));
    assert_eq!(mock.requests().len(), 2);
    let source = fixture.runs.join("prepared");
    let before = fs::read(source.join("events.jsonl"))?;
    let mut reviewer = Decline { targets: Vec::new() };
    assert!(run_prepared(&prepared.prepared, "child".into(), fixture.paths.clone(), &mut reviewer).await.is_err());
    assert_eq!(reviewer.targets.len(), 1);
    assert_eq!(reviewer.targets[0].run_id, "child");
    assert_eq!(reviewer.targets[0].content_sha256, plan.digest()?);
    assert_eq!(mock.requests().len(), 2);
    assert!(!fixture.repository.join("greeting.txt").exists());
    assert_eq!(fs::read(source.join("events.jsonl"))?, before);
    let parent: Value = serde_json::from_slice(&fs::read(fixture.runs.join("child/evidence/parent-preparation.json"))?)?;
    assert_eq!(parent["approval_reused"], false);
    Ok(())
}
