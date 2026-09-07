#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use codex_lab::WorkflowState;
use codex_lab_runtime::HumanDecision;
use codex_lab_runtime::HumanReviewer;
use codex_lab_runtime::execute_run;
use core_test_support::responses;
use core_test_support::responses::ResponseMock;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use wiremock::MockServer;

const PATCH: &str = "*** Begin Patch\n*** Add File: greeting.txt\n+hello\n*** End Patch";
const FORBIDDEN_PATCH: &str =
    "*** Begin Patch\n*** Add File: forbidden.txt\n+unapproved\n*** End Patch";

struct Reviewer {
    repository: PathBuf,
    targets: Vec<ApprovalTarget>,
    views: Vec<Vec<u8>>,
    responses: Option<ResponseMock>,
    expected_requests_at_review: Vec<usize>,
    approve: bool,
}

impl HumanReviewer for Reviewer {
    fn review(
        &mut self,
        target: &ApprovalTarget,
        rendered: &RenderedPlan,
    ) -> Result<HumanDecision> {
        ensure!(
            !self.repository.join("greeting.txt").exists(),
            "implementation began before explicit approval"
        );
        ensure!(
            !self.repository.join("forbidden.txt").exists(),
            "unapproved write reached the repository"
        );
        let expected = self
            .expected_requests_at_review
            .get(self.targets.len())
            .context("unexpected extra human review")?;
        assert_eq!(
            self.responses
                .as_ref()
                .map_or(0, |responses| responses.requests().len()),
            *expected
        );
        self.targets.push(target.clone());
        self.views.push(rendered.content.clone());
        Ok(if self.approve {
            HumanDecision::Approve(target.clone())
        } else {
            HumanDecision::Abort
        })
    }
}

fn response(id: &str, item: Value) -> String {
    responses::sse(vec![
        responses::ev_response_created(id),
        item,
        responses::ev_completed_with_tokens(id, 7),
    ])
}

fn implementation_and_verification(prefix: &str) -> Vec<String> {
    let call = format!("{prefix}-verify");
    vec![
        response(&format!("{prefix}-implementation-call"), responses::ev_custom_tool_call(&format!("{prefix}-patch"), "apply_patch", PATCH)),
        response(&format!("{prefix}-implementation-done"), responses::ev_assistant_message("implementation", "{\"completed_steps\":[\"S01\"]}")),
        response(&format!("{prefix}-verification-call"), responses::ev_function_call(&call, "exec_command", &json!({
            "cmd":"test \"$(cat greeting.txt)\" = hello && test ! -e forbidden.txt",
            "max_output_tokens":1024, "timeout_ms":5000
        }).to_string())),
        response(&format!("{prefix}-verification-done"), responses::ev_assistant_message("verification", &json!({
            "checks":[{"verification_id":"V01","call_id":call,"acceptance_criteria":["AC01"]}]
        }).to_string())),
    ]
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn generated_workflow_enforces_review_before_real_patch_and_verification() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let canonical = support::plan(1)?;
    let mut sequence = vec![
        response(
            "research-blocked",
            responses::ev_custom_tool_call("unapproved-patch", "apply_patch", FORBIDDEN_PATCH),
        ),
        response(
            "research-read",
            responses::ev_function_call(
                "research-read",
                "lab_repo_read",
                "{\"path\":\"README.md\"}",
            ),
        ),
        response(
            "research-complete",
            responses::ev_assistant_message(
                "research",
                "README.md defines the task. Create greeting.txt and verify its exact contents.",
            ),
        ),
        response(
            "plan-generated",
            responses::ev_assistant_message("plan", &serde_json::to_string(&canonical)?),
        ),
    ];
    sequence.extend(implementation_and_verification("generated"));
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: Vec::new(),
        views: Vec::new(),
        responses: Some(mock.clone()),
        expected_requests_at_review: vec![4],
        approve: true,
    };
    let result = execute_run(
        fixture.options("generated", "md", None),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .inspect_err(|error| eprintln!("generated workflow failed: {error:#}"))?;
    assert_eq!(
        (result.state, result.phase_threads, reviewer.targets.len()),
        (WorkflowState::Completed, 4, 1)
    );
    assert_eq!(
        std::fs::read(fixture.repository.join("greeting.txt"))?,
        b"hello\n"
    );
    assert!(!fixture.repository.join("forbidden.txt").exists());
    assert_eq!(
        std::fs::read(result.artifacts.join("plans/1/plan.json"))?,
        canonical.canonical_json()?
    );
    let denial = mock
        .requests()
        .iter()
        .flat_map(core_test_support::responses::ResponsesRequest::input)
        .find(|item| {
            item["type"] == "custom_tool_call_output" && item["call_id"] == "unapproved-patch"
        })
        .context("missing rejected tool result")?;
    assert!(denial.to_string().contains("admission") || denial.to_string().contains("phase"));
    let metrics: Value = serde_json::from_slice(&std::fs::read(
        result.artifacts.join("evidence/metrics.json"),
    )?)?;
    assert_eq!(
        (
            metrics["verification_ready"].clone(),
            metrics["first_plan_human_approval"].clone(),
            metrics["files_changed"].clone()
        ),
        (json!(true), json!(true), json!(1))
    );
    assert!(
        String::from_utf8(std::fs::read(result.artifacts.join("evidence/final.diff"))?)?
            .contains("+hello")
    );
    assert_eq!(mock.requests().len(), 8);
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn reused_canonical_plan_is_identical_across_markdown_and_json_runs() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let canonical = support::plan(1)?;
    let mut sequence = implementation_and_verification("md");
    sequence.extend(implementation_and_verification("json"));
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: Vec::new(),
        views: Vec::new(),
        responses: Some(mock.clone()),
        expected_requests_at_review: vec![0, 4],
        approve: true,
    };
    let md = execute_run(
        fixture.options("md", "md", Some(canonical.clone())),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .inspect_err(|error| eprintln!("Markdown workflow failed: {error:#}"))?;
    std::fs::remove_file(fixture.repository.join("greeting.txt"))?;
    let structured = execute_run(
        fixture.options("json", "json", Some(canonical.clone())),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .inspect_err(|error| eprintln!("JSON workflow failed: {error:#}"))?;
    assert_eq!(
        (
            md.state,
            structured.state,
            md.phase_threads,
            structured.phase_threads
        ),
        (WorkflowState::Completed, WorkflowState::Completed, 2, 2)
    );
    assert_eq!(
        std::fs::read(md.artifacts.join("plans/1/plan.json"))?,
        std::fs::read(structured.artifacts.join("plans/1/plan.json"))?
    );
    assert_eq!(
        reviewer.targets[0].content_sha256,
        reviewer.targets[1].content_sha256
    );
    assert_ne!(reviewer.targets[0].run_id, reviewer.targets[1].run_id);
    assert_ne!(reviewer.views[0], reviewer.views[1]);
    let mut md_config: Value = serde_json::from_slice(&std::fs::read(
        md.artifacts.join("config/workflow.effective.json"),
    )?)?;
    let mut json_config: Value = serde_json::from_slice(&std::fs::read(
        structured.artifacts.join("config/workflow.effective.json"),
    )?)?;
    md_config["plan"]["renderer"] = Value::Null;
    json_config["plan"]["renderer"] = Value::Null;
    assert_eq!(md_config, json_config);
    for role in ["planner", "executor", "verifier"] {
        let path = format!("instructions/{role}.SKILL.md");
        assert_eq!(
            std::fs::read(md.artifacts.join(&path))?,
            std::fs::read(structured.artifacts.join(&path))?
        );
    }
    assert_eq!(
        std::fs::read(md.artifacts.join("evidence/effective-settings.json"))?,
        std::fs::read(
            structured
                .artifacts
                .join("evidence/effective-settings.json")
        )?
    );
    let md_input: Value =
        serde_json::from_slice(&std::fs::read(md.artifacts.join("evidence/input-01.json"))?)?;
    let json_input: Value = serde_json::from_slice(&std::fs::read(
        structured.artifacts.join("evidence/input-01.json"),
    )?)?;
    assert_eq!(
        (&md_input["instructions"], &md_input["output_schema"]),
        (&json_input["instructions"], &json_input["output_schema"])
    );
    assert_ne!(md_input["prompt"], json_input["prompt"]);
    assert_eq!(mock.requests().len(), 8);
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn declining_review_never_starts_a_model_or_changes_repository() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: Vec::new(),
        views: Vec::new(),
        responses: None,
        expected_requests_at_review: vec![0],
        approve: false,
    };
    let result = execute_run(
        fixture.options("declined", "md", Some(support::plan(1)?)),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await;
    let error = result.expect_err("declined approval must abort");
    assert!(
        error
            .to_string()
            .contains("human review ended without approval"),
        "{error:#}"
    );
    assert_eq!(reviewer.targets.len(), 1);
    assert!(!fixture.repository.join("greeting.txt").exists());
    assert!(
        server
            .received_requests()
            .await
            .context("mock request recording disabled")?
            .is_empty()
    );
    let journal = std::fs::read_to_string(fixture.runs.join("declined/events.jsonl"))?;
    assert!(journal.contains("failed"));
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn oversized_plan_fails_before_human_review_or_any_model_call() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut canonical = support::plan(1)?;
    canonical.goal = "x".repeat(8192);
    canonical.validate()?;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: Vec::new(),
        views: Vec::new(),
        responses: None,
        expected_requests_at_review: Vec::new(),
        approve: true,
    };
    let error = execute_run(
        fixture.options("oversized", "md", Some(canonical)),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .expect_err("the full plan must fit before seeking approval");
    assert!(error.to_string().contains("byte limit"), "{error:#}");
    assert!(reviewer.targets.is_empty());
    assert!(
        server
            .received_requests()
            .await
            .context("mock request recording disabled")?
            .is_empty()
    );
    assert!(!fixture.repository.join("greeting.txt").exists());
    let journal = std::fs::read_to_string(fixture.runs.join("oversized/events.jsonl"))?;
    assert!(journal.contains("failed"));
    assert!(
        !fixture
            .runs
            .join("oversized/evidence/metrics.json")
            .exists()
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn amendment_stops_the_old_thread_and_requires_a_new_exact_approval() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let amended = support::plan(2)?;
    let reason =
        "Repository research requires explicit verification that forbidden.txt remains absent.";
    let mut sequence = vec![
        response(
            "amendment-request",
            responses::ev_function_call(
                "amend",
                "lab_request_amendment",
                &json!({"reason":reason}).to_string(),
            ),
        ),
        response(
            "amended-plan",
            responses::ev_assistant_message("plan", &serde_json::to_string(&amended)?),
        ),
    ];
    sequence.extend(implementation_and_verification("amended"));
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: Vec::new(),
        views: Vec::new(),
        responses: Some(mock.clone()),
        expected_requests_at_review: vec![0, 2],
        approve: true,
    };
    let result = execute_run(
        fixture.options("amended", "md", Some(support::plan(1)?)),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .inspect_err(|error| eprintln!("amended workflow failed: {error:#}"))?;
    assert_eq!(
        (result.state, result.phase_threads, reviewer.targets.len()),
        (WorkflowState::Completed, 4, 2)
    );
    assert_eq!(reviewer.targets[0].run_id, reviewer.targets[1].run_id);
    assert_ne!(
        reviewer.targets[0].content_sha256,
        reviewer.targets[1].content_sha256
    );
    assert_eq!(
        std::fs::read(result.artifacts.join("plans/2/plan.json"))?,
        amended.canonical_json()?
    );
    let phase: Value = serde_json::from_slice(&std::fs::read(
        result.artifacts.join("evidence/phase-01.json"),
    )?)?;
    assert_eq!(phase["cancelled"], true);
    let planning_input: Value = serde_json::from_slice(&std::fs::read(
        result.artifacts.join("evidence/input-02.json"),
    )?)?;
    assert!(
        planning_input["prompt"]
            .as_str()
            .context("planning prompt")?
            .contains(reason)
    );
    let trace = std::fs::read_to_string(result.artifacts.join("runtime-events.jsonl"))?
        .lines()
        .map(serde_json::from_str::<Value>)
        .collect::<serde_json::Result<Vec<_>>>()?;
    let revoked = trace
        .iter()
        .position(|event| event["type"] == "admission_revoked")
        .context("revocation missing")?;
    let stopped = trace
        .iter()
        .position(|event| event["type"] == "phase_stopped")
        .context("shutdown observation missing")?;
    let next_phase = trace
        .iter()
        .position(|event| event["type"] == "phase_started" && event["epoch"] == 2)
        .context("new phase missing")?;
    assert!(revoked < stopped && stopped < next_phase);
    let metrics: Value = serde_json::from_slice(&std::fs::read(
        result.artifacts.join("evidence/metrics.json"),
    )?)?;
    assert_eq!(metrics["plan_amendments"], 1);
    assert_eq!(mock.requests().len(), 6);
    Ok(())
}
