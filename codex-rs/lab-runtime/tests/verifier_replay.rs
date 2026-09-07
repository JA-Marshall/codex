#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use anyhow::Result;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use codex_lab::WorkflowState;
use codex_lab_runtime::HumanDecision;
use codex_lab_runtime::HumanReviewer;
use codex_lab_runtime::VerificationInput;
use codex_lab_runtime::prepare_run;
use codex_lab_runtime::run_prepared;
use core_test_support::responses;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use sha2::Digest;
use wiremock::MockServer;

struct Review {
    mock: responses::ResponseMock,
    approve: bool,
}

impl HumanReviewer for Review {
    fn review(&mut self, target: &ApprovalTarget, _: &RenderedPlan) -> Result<HumanDecision> {
        assert_eq!(self.mock.requests().len(), 0);
        Ok(if self.approve { HumanDecision::Approve(target.clone()) } else { HumanDecision::Abort })
    }
}

async fn candidate(server: &MockServer) -> Result<support::Fixture> {
    let mut fixture = support::Fixture::new(&server.uri()).await?;
    std::fs::write(fixture.repository.join("greeting.txt"), "hello\n")?;
    support::git(&fixture.repository, &["add", "greeting.txt"]).await?;
    support::git(&fixture.repository, &["-c", "user.name=Lab test", "-c", "user.email=lab@example.invalid", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "frozen candidate"]).await?;
    fixture.commit = support::git(&fixture.repository, &["rev-parse", "HEAD"]).await?.trim().into();
    Ok(fixture)
}

fn input(fixture: &support::Fixture) -> Result<VerificationInput> {
    VerificationInput::from_json(&serde_json::to_vec(&json!({
        "schema_version":1,"candidate_commit":fixture.commit,
        "plan_sha256":format!("{:x}", sha2::Sha256::digest(support::plan(1)?.canonical_json()?)),
        "source_run":"frozen-source","source_phase_sha256":"b".repeat(64),
        "implementation_report":{"completed_steps":["S01"]}
    }))?)
}

fn response(id: &str, item: Value) -> String {
    responses::sse(vec![responses::ev_response_created(id), item, responses::ev_completed_with_tokens(id, 7)])
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn verifier_replay_seals_inputs_and_runs_only_verification_after_fresh_approval() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = candidate(&server).await?;
    let mock = responses::mount_sse_sequence(&server, vec![
        response("verify", responses::ev_function_call("verify", "exec_command", &json!({"cmd":"test \"$(cat greeting.txt)\" = hello"}).to_string())),
        response("receipt", responses::ev_function_call("receipt", "lab_command_receipt", "{\"index\":1}")),
        response("done", responses::ev_assistant_message("done", "{\"checks\":[{\"verification_id\":\"V01\",\"call_id\":\"verify\",\"acceptance_criteria\":[\"AC01\"]}]}")),
    ]).await;
    let mut options = fixture.options("prepared", "md", Some(support::plan(1)?));
    options.verification_input = Some(input(&fixture)?);
    let prepared = prepare_run(options, fixture.paths.clone()).await?;
    assert_eq!((prepared.state, prepared.phase_threads, mock.requests().len()), (WorkflowState::AwaitingPlanApproval, 0, 0));
    let sealed_path = prepared.prepared.parent().unwrap().join("verification-input.json");
    let original = std::fs::read(&sealed_path)?;
    std::fs::write(&sealed_path, b"{}")?;
    assert!(run_prepared(&prepared.prepared, "tampered".into(), fixture.paths.clone(), &mut Review {mock: mock.clone(), approve:true}).await.is_err());
    std::fs::write(&sealed_path, &original)?;
    assert!(run_prepared(&prepared.prepared, "unapproved".into(), fixture.paths.clone(), &mut Review {mock: mock.clone(), approve:false}).await.is_err());
    assert_eq!(mock.requests().len(), 0);
    let result = run_prepared(&prepared.prepared, "approved".into(), fixture.paths.clone(), &mut Review {mock:mock.clone(), approve:true}).await?;
    assert_eq!((result.state, result.phase_threads, mock.requests().len()), (WorkflowState::Completed, 1, 3));
    assert_eq!(std::fs::read(result.artifacts.join("evidence/verification-input.json"))?, original);
    let phase: Value = serde_json::from_slice(&std::fs::read(result.artifacts.join("evidence/input-01.json"))?)?;
    assert_eq!(phase["phase"], "verification");
    assert!(phase["prompt"].as_str().unwrap().contains("Imported implementation report"));
    let journal = std::fs::read_to_string(result.artifacts.join("events.jsonl"))?;
    assert!(journal.contains("verification-input.json#implementation_report"));
    let spec: Value = serde_json::from_slice(&std::fs::read(result.artifacts.join("config/run-spec.json"))?)?;
    assert_eq!(spec["verification_input_sha256"], format!("{:x}", sha2::Sha256::digest(&original)));
    assert_eq!(std::fs::read(fixture.repository.join("greeting.txt"))?, b"hello\n");
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn verifier_replay_amendment_stops_without_replanning_or_executor_calls() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = candidate(&server).await?;
    let mock = responses::mount_sse_sequence(&server, vec![response("amend", responses::ev_function_call("amend", "lab_request_amendment", "{\"reason\":\"Frozen plan requires a material change\"}"))]).await;
    let mut options = fixture.options("prepared", "md", Some(support::plan(1)?));
    options.verification_input = Some(input(&fixture)?);
    let prepared = prepare_run(options, fixture.paths.clone()).await?;
    let error = run_prepared(&prepared.prepared, "amended".into(), fixture.paths.clone(), &mut Review {mock:mock.clone(), approve:true}).await.unwrap_err();
    assert!(error.to_string().contains("verifier-only amendment requires a new preparation"));
    assert_eq!(mock.requests().len(), 1);
    let journal = std::fs::read_to_string(fixture.runs.join("amended/runtime-events.jsonl"))?;
    assert!(journal.contains("phase_stopped"));
    assert!(!journal.contains("\"phase\":\"planning\"") && !journal.contains("\"phase\":\"implementation\""));
    Ok(())
}
