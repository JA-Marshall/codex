#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use std::path::PathBuf;
use std::sync::atomic::AtomicUsize;
use std::sync::atomic::Ordering;

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
use wiremock::Mock;
use wiremock::MockServer;
use wiremock::Request;
use wiremock::ResponseTemplate;
use wiremock::matchers::method;
use wiremock::matchers::path;

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
        response(&format!("{prefix}-receipt"), responses::ev_function_call(&format!("{prefix}-receipt"), "lab_command_receipt", "{\"index\":1}")),
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
    let receipt = mock
        .requests()
        .last()
        .context("verification request")?
        .function_call_output_text("generated-receipt")
        .context("missing command receipt")?;
    let receipt: Value = serde_json::from_str(&receipt)
        .with_context(|| format!("actual receipt output: {receipt}"))?;
    assert_eq!(receipt["receipt"]["call_id"], "generated-verify");
    assert_eq!(
        receipt["receipt"]["tool_outcome"],
        json!({"status":"completed","success":true})
    );
    assert_eq!(mock.requests().len(), 9);
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
        expected_requests_at_review: vec![0, 5],
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
    assert_eq!(mock.requests().len(), 10);
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
    assert_eq!(mock.requests().len(), 7);
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn displayed_chunk_id_still_fails_after_a_passing_command_and_valid_receipt() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let sequence = implementation_and_verification("chunk");
    let position = AtomicUsize::new(0);
    Mock::given(method("POST")).and(path("/v1/responses")).respond_with(move |request: &Request| {
        let index = position.fetch_add(1, Ordering::SeqCst);
        let body = if index < 4 { sequence[index].clone() } else {
            let request: Value = serde_json::from_slice(&request.body).expect("valid request JSON");
            let inputs = request["input"].as_array().expect("request inputs");
            let output = inputs.iter().find(|item| item["type"] == "function_call_output" && item["call_id"] == "chunk-verify")
                .expect("actual command result")["output"].as_str().expect("command output");
            let chunk_id = output.lines().find_map(|line| line.strip_prefix("Chunk ID: ")).expect("displayed chunk ID");
            let receipt = inputs.iter().find(|item| item["type"] == "function_call_output" && item["call_id"] == "chunk-receipt").expect("receipt output");
            let receipt: Value = serde_json::from_str(receipt["output"].as_str().expect("receipt JSON text")).expect("receipt JSON");
            assert_eq!(receipt["receipt"]["call_id"], "chunk-verify");
            assert_ne!(chunk_id, "chunk-verify");
            response("wrong-reference", responses::ev_assistant_message("verification", &json!({
                "checks":[{"verification_id":"V01","call_id":chunk_id,"acceptance_criteria":["AC01"]}]
            }).to_string()))
        };
        ResponseTemplate::new(200).insert_header("content-type", "text/event-stream").set_body_string(body)
    }).mount(&server).await;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: vec![],
        views: vec![],
        responses: None,
        expected_requests_at_review: vec![0],
        approve: true,
    };
    let error = execute_run(
        fixture.options("chunk", "md", Some(support::plan(1)?)),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .expect_err("displayed chunk cannot replace the host call ID");
    assert!(
        error
            .to_string()
            .contains("verification did not reference a completed host command")
    );
    assert_eq!(
        std::fs::read(fixture.repository.join("greeting.txt"))?,
        b"hello\n"
    );
    let journal = std::fs::read_to_string(fixture.runs.join("chunk/events.jsonl"))?;
    let last: Value = serde_json::from_str(journal.lines().last().context("last workflow event")?)?;
    assert_eq!(last["state"], "failed");
    assert!(!fixture.runs.join("chunk/evidence/metrics.json").exists());
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn planner_prose_reference_fails_domain_validation_before_review() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut canonical = support::plan(1)?;
    canonical.steps[0].verification = vec!["Run V01 Python byte check read-only.".into()];
    let mock = responses::mount_sse_sequence(
        &server,
        vec![
            response(
                "research",
                responses::ev_assistant_message("research", "Create greeting.txt and run Python."),
            ),
            response(
                "plan",
                responses::ev_assistant_message("plan", &serde_json::to_string(&canonical)?),
            ),
        ],
    )
    .await;
    let mut reviewer = Reviewer {
        repository: fixture.repository.clone(),
        targets: vec![],
        views: vec![],
        responses: Some(mock.clone()),
        expected_requests_at_review: vec![],
        approve: true,
    };
    let error = execute_run(
        fixture.options("invalid-reference", "md", None),
        fixture.paths.clone(),
        &mut reviewer,
    )
    .await
    .expect_err("prose is not a verification ID");
    assert!(error.to_string().contains("plan IDs require"), "{error:#}");
    assert!(reviewer.targets.is_empty());
    assert!(!fixture.repository.join("greeting.txt").exists());
    assert_eq!(mock.requests().len(), 2);
    Ok(())
}
