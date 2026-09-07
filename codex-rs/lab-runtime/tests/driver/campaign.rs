use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use codex_lab::WorkflowState;
use codex_lab_runtime::HumanDecision;
use codex_lab_runtime::HumanReviewer;
use codex_lab_runtime::RunOptions;
use codex_lab_runtime::execute_campaign_run;
use codex_lab_runtime::execute_run;
use core_test_support::responses;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use sha2::Digest;
use tokio::process::Command;
use tokio::time::timeout;
use wiremock::MockServer;

use super::implementation_and_verification;
use super::response;
use super::support;

pub(super) fn policy(options: &RunOptions, max_amendments: u8) -> Value {
    json!({
        "schema_version":1,"campaign_id":"campaign-test","run_id":options.run_id,
        "repository":options.repository,"repository_commit":options.repository_commit,
        "task_sha256":format!("{:x}",sha2::Sha256::digest(options.task.as_bytes())),
        "workflow":options.workflow,
        "workflow_catalog_sha256":format!("{:x}",sha2::Sha256::digest(options.workflow_catalog.as_bytes())),
        "max_amendments":max_amendments
    })
}

fn write_policy(
    fixture: &support::Fixture,
    options: &RunOptions,
    max_amendments: u8,
) -> Result<PathBuf> {
    let path = fixture.runs.join(format!("{}-policy.json", options.run_id));
    std::fs::write(
        &path,
        serde_json::to_vec_pretty(&policy(options, max_amendments))?,
    )?;
    Ok(path)
}

pub(super) fn campaign_options(fixture: &support::Fixture, id: &str) -> RunOptions {
    let mut options = fixture.options(id, "md", None);
    options.workflow_catalog = options
        .workflow_catalog
        .replace("human_required", "campaign_delegated");
    options
}

fn delegated_events(artifacts: &std::path::Path) -> Result<Vec<Value>> {
    Ok(std::fs::read_to_string(artifacts.join("events.jsonl"))?
        .lines()
        .map(serde_json::from_str::<Value>)
        .collect::<serde_json::Result<Vec<_>>>()?
        .into_iter()
        .filter(|event| event["change"]["type"] == "delegated_approved")
        .collect())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn campaign_cli_generates_and_repairs_with_long_receipts_and_stdin_closed() -> Result<()> {
    let server = MockServer::start().await;
    let mut fixture = support::Fixture::new(&server.uri()).await?;
    fixture.workflow_catalog = fixture
        .workflow_catalog
        .replace("[workflows.base]", "[workflows.base]\nmax_repairs = 1");
    let options = campaign_options(&fixture, "campaign-generated");
    let policy_path = write_policy(&fixture, &options, 0)?;
    let mut sequence = vec![
        response(
            "research",
            responses::ev_assistant_message("research", "Create greeting.txt and verify it."),
        ),
        response(
            "plan",
            responses::ev_assistant_message("plan", &serde_json::to_string(&support::plan(1)?)?),
        ),
    ];
    let mut initial = implementation_and_verification("campaign");
    initial[0] = initial[0].replace("+hello", "+wrong");
    sequence.extend(initial);
    let mut repair = implementation_and_verification("repair");
    repair[0] = response(
        "repair-patch",
        responses::ev_custom_tool_call(
            "repair-patch",
            "apply_patch",
            "*** Begin Patch\n*** Update File: greeting.txt\n@@\n-wrong\n+hello\n*** End Patch",
        ),
    );
    sequence.extend(repair);
    for event in &mut sequence {
        *event = event.replace(
            "&& test ! -e forbidden.txt",
            &format!("&& test ! -e forbidden.txt # {}", "x".repeat(16384)),
        );
    }
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let task = fixture.home.join("task.txt");
    let catalog = fixture.home.join("workflows.toml");
    std::fs::write(&task, &options.task)?;
    std::fs::write(&catalog, &options.workflow_catalog)?;
    let output = timeout(
        Duration::from_secs(60),
        Command::new(
            fixture
                .paths
                .codex_self_exe
                .as_ref()
                .context("CLI binary missing")?,
        )
        .env("CODEX_HOME", &fixture.home)
        .current_dir(&fixture.repository)
        .arg("run")
        .arg("--repository")
        .arg(&fixture.repository)
        .arg("--commit")
        .arg(&fixture.commit)
        .arg("--codex-home")
        .arg(&fixture.home)
        .arg("--runs-directory")
        .arg(&fixture.runs)
        .args(["--run-id", &options.run_id, "--workflow", &options.workflow])
        .arg("--task-file")
        .arg(task)
        .arg("--workflow-catalog")
        .arg(catalog)
        .arg("--instruction-root")
        .arg(&fixture.instruction_root)
        .arg("--campaign-policy")
        .arg(&policy_path)
        .stdin(Stdio::null())
        .kill_on_drop(true)
        .output(),
    )
    .await??;
    ensure!(
        output.status.success(),
        "campaign CLI failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: Value = serde_json::from_slice(&output.stdout)?;
    assert_eq!(
        (
            result["state"].clone(),
            result["phase_threads"].clone(),
            mock.requests().len()
        ),
        (json!("completed"), json!(6), 12)
    );
    let artifacts = PathBuf::from(
        result["artifacts"]
            .as_str()
            .context("result artifact path")?,
    );
    let bytes = std::fs::read(&policy_path)?;
    assert_eq!(
        std::fs::read(artifacts.join("evidence/campaign-policy.json"))?,
        bytes
    );
    let events = delegated_events(&artifacts)?;
    assert_eq!(events.len(), 1);
    assert_eq!(
        events[0]["change"]["policy_sha256"],
        format!("{:x}", sha2::Sha256::digest(&bytes))
    );
    let metrics: Value =
        serde_json::from_slice(&std::fs::read(artifacts.join("evidence/metrics.json"))?)?;
    assert_eq!(
        (
            metrics["first_plan_human_approval"].clone(),
            metrics["delegated_plan_approvals"].clone()
        ),
        (Value::Null, json!(1))
    );
    assert_eq!(metrics["repair_attempts"], 1);
    for prefix in ["campaign", "repair"] {
        let output = mock
            .requests()
            .iter()
            .find_map(|request| request.function_call_output_text(&format!("{prefix}-receipt")))
            .context("missing long-command receipt")?;
        let receipt: Value = serde_json::from_str(&output)?;
        assert_eq!(receipt["receipt"]["call_id"], format!("{prefix}-verify"));
        assert_eq!(receipt["receipt"]["preview_truncated"], true);
    }
    let journal = std::fs::read_to_string(artifacts.join("events.jsonl"))?;
    assert!(journal.lines().any(|line| {
        serde_json::from_str::<Value>(line).is_ok_and(|event| {
            event["change"]["type"] == "verification_recorded"
                && event["change"]["evidence"]["passed"] == false
        })
    }));
    for phase in 1..=6 {
        let evidence: Value = serde_json::from_slice(&std::fs::read(
            artifacts.join(format!("evidence/phase-{phase:02}.json")),
        )?)?;
        assert!(
            evidence["events"]
                .as_array()
                .context("phase events")?
                .iter()
                .any(|event| event["msg"]["type"] == "shutdown_complete")
        );
    }
    assert_eq!(
        std::fs::read(fixture.repository.join("greeting.txt"))?,
        b"hello\n"
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn campaign_stops_at_amendment_limit_before_replanning() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut options = campaign_options(&fixture, "campaign-limit");
    options.plan = Some(support::plan(1)?);
    let policy_path = write_policy(&fixture, &options, 0)?;
    let mock = responses::mount_sse_sequence(
        &server,
        vec![response(
            "amendment",
            responses::ev_function_call(
                "amend",
                "lab_request_amendment",
                "{\"reason\":\"A new plan is required.\"}",
            ),
        )],
    )
    .await;
    let error = execute_campaign_run(options, fixture.paths.clone(), &policy_path)
        .await
        .expect_err("amendment exceeds delegated limit");
    assert!(
        error
            .to_string()
            .contains("campaign amendment limit exceeded (0)"),
        "{error:#}"
    );
    assert_eq!(mock.requests().len(), 1);
    let artifacts = fixture.runs.join("campaign-limit");
    assert_eq!(delegated_events(&artifacts)?.len(), 1);
    assert!(!artifacts.join("plans/2").exists());
    let journal = std::fs::read_to_string(artifacts.join("events.jsonl"))?;
    let last: Value = serde_json::from_str(journal.lines().last().context("last workflow event")?)?;
    assert_eq!(last["state"], "failed");
    assert!(!fixture.repository.join("greeting.txt").exists());
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn campaign_approves_fresh_amended_target_within_limit() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut options = campaign_options(&fixture, "campaign-amended");
    options.plan = Some(support::plan(1)?);
    let policy_path = write_policy(&fixture, &options, 1)?;
    let mut sequence = vec![
        response(
            "amendment",
            responses::ev_function_call(
                "amend",
                "lab_request_amendment",
                "{\"reason\":\"Add explicit forbidden-file verification.\"}",
            ),
        ),
        response(
            "amended-plan",
            responses::ev_assistant_message("plan", &serde_json::to_string(&support::plan(2)?)?),
        ),
    ];
    sequence.extend(implementation_and_verification("campaign-amended"));
    let mock = responses::mount_sse_sequence(&server, sequence).await;
    let result = execute_campaign_run(options, fixture.paths.clone(), &policy_path).await?;
    let events = delegated_events(&result.artifacts)?;
    assert_eq!(
        (result.state, events.len(), mock.requests().len()),
        (WorkflowState::Completed, 2, 7)
    );
    assert_ne!(events[0]["change"]["target"], events[1]["change"]["target"]);
    assert_eq!(
        events[0]["change"]["policy_sha256"],
        events[1]["change"]["policy_sha256"]
    );
    Ok(())
}

struct UnboundDelegation;

impl HumanReviewer for UnboundDelegation {
    fn review(&mut self, target: &ApprovalTarget, _: &RenderedPlan) -> Result<HumanDecision> {
        Ok(HumanDecision::ApproveDelegated {
            target: target.clone(),
            policy_sha256: "a".repeat(64),
        })
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn manual_run_rejects_delegated_decision_without_bound_policy() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let options = fixture.options("manual-delegation", "md", Some(support::plan(1)?));
    let error = execute_run(options, fixture.paths.clone(), &mut UnboundDelegation)
        .await
        .expect_err("manual run cannot delegate");
    assert!(
        error.to_string().contains("validated campaign policy"),
        "{error:#}"
    );
    assert!(
        server
            .received_requests()
            .await
            .context("recorded requests")?
            .is_empty()
    );
    assert!(!fixture.repository.join("greeting.txt").exists());
    let options = campaign_options(&fixture, "missing-policy");
    let error = execute_run(options, fixture.paths.clone(), &mut UnboundDelegation)
        .await
        .expect_err("delegated workflow requires a policy before research");
    assert!(
        error
            .to_string()
            .contains("requires a validated campaign policy"),
        "{error:#}"
    );
    assert!(
        server
            .received_requests()
            .await
            .context("recorded requests")?
            .is_empty()
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn campaign_rejects_changed_task_catalog_and_manual_workflow_before_model_calls() -> Result<()>
{
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let mut options = campaign_options(&fixture, "wrong-task");
    let path = write_policy(&fixture, &options, 0)?;
    options.task.push_str(" Expand the task.");
    let error = execute_campaign_run(options, fixture.paths.clone(), &path)
        .await
        .expect_err("task is frozen");
    assert!(
        error.to_string().contains("task digest mismatch"),
        "{error:#}"
    );
    let mut options = campaign_options(&fixture, "wrong-catalog");
    let path = write_policy(&fixture, &options, 0)?;
    options.workflow_catalog.push_str("\n# changed catalog\n");
    let error = execute_campaign_run(options, fixture.paths.clone(), &path)
        .await
        .expect_err("catalog bytes are frozen");
    assert!(
        error.to_string().contains("catalog digest mismatch"),
        "{error:#}"
    );
    let options = fixture.options("manual-workflow", "md", None);
    let path = write_policy(&fixture, &options, 0)?;
    let error = execute_campaign_run(options, fixture.paths.clone(), &path)
        .await
        .expect_err("manual workflow cannot delegate");
    assert!(
        error
            .to_string()
            .contains("requires a campaign_delegated workflow"),
        "{error:#}"
    );
    let options = campaign_options(&fixture, "untrusted-policy");
    let path = fixture.repository.join("policy.json");
    std::fs::write(&path, serde_json::to_vec(&policy(&options, 0))?)?;
    let error = execute_campaign_run(options, fixture.paths.clone(), &path)
        .await
        .expect_err("model-writable policy rejected");
    assert!(
        error
            .to_string()
            .contains("outside the model-writable repository"),
        "{error:#}"
    );
    assert!(
        server
            .received_requests()
            .await
            .context("recorded requests")?
            .is_empty()
    );
    Ok(())
}
