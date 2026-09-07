#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use std::fs;
use std::path::Path;
use std::process::Stdio;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use core_test_support::responses;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use tokio::io::AsyncBufReadExt;
use tokio::io::AsyncReadExt;
use tokio::io::AsyncWriteExt;
use tokio::io::BufReader;
use tokio::process::Command;
use tokio::time::timeout;
use wiremock::MockServer;

fn child(fixture: &support::Fixture) -> Result<Command> {
    let mut command = Command::new(
        fixture
            .paths
            .codex_self_exe
            .as_ref()
            .context("CLI binary missing")?,
    );
    command
        .env("CODEX_HOME", &fixture.home)
        .current_dir(&fixture.repository)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    Ok(command)
}

async fn prepare(
    fixture: &support::Fixture,
    id: &str,
    workflow: &str,
) -> Result<std::path::PathBuf> {
    let task = fixture.home.join("task.txt");
    let catalog = fixture.home.join("workflows.toml");
    let plan = fixture.home.join("plan.json");
    fs::write(&task, fixture.options("unused", "md", None).task)?;
    fs::write(&catalog, &fixture.workflow_catalog)?;
    fs::write(&plan, support::plan(1)?.canonical_json()?)?;
    let result = timeout(
        Duration::from_secs(45),
        child(fixture)?
            .arg("prepare")
            .arg("--repository")
            .arg(&fixture.repository)
            .arg("--commit")
            .arg(&fixture.commit)
            .arg("--codex-home")
            .arg(&fixture.home)
            .arg("--runs-directory")
            .arg(&fixture.runs)
            .args(["--run-id", id, "--workflow", workflow])
            .arg("--task-file")
            .arg(task)
            .arg("--workflow-catalog")
            .arg(catalog)
            .arg("--instruction-root")
            .arg(&fixture.instruction_root)
            .arg("--plan-file")
            .arg(plan)
            .output(),
    )
    .await??;
    ensure!(
        result.status.success(),
        "prepare failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    let result: Value = serde_json::from_slice(&result.stdout)?;
    assert_eq!(result["state"], "awaiting_plan_approval");
    Ok(result["prepared"]
        .as_str()
        .context("missing checkpoint")?
        .into())
}

fn execution(fixture: &support::Fixture, prepared: &Path, id: &str) -> Result<Command> {
    let mut command = child(fixture)?;
    command
        .arg("run-prepared")
        .arg("--prepared")
        .arg(prepared)
        .args(["--run-id", id]);
    Ok(command)
}

fn successful_responses() -> Vec<String> {
    [
        responses::ev_custom_tool_call("patch", "apply_patch", "*** Begin Patch\n*** Add File: greeting.txt\n+hello\n*** End Patch"),
        responses::ev_assistant_message("implemented", "{\"completed_steps\":[\"S01\"]}"),
        responses::ev_function_call("verify", "exec_command", &json!({"cmd":"test \"$(cat greeting.txt)\" = hello && test ! -e forbidden.txt", "max_output_tokens":1024,"timeout_ms":5000}).to_string()),
        responses::ev_function_call("receipt", "lab_command_receipt", "{\"index\":1}"),
        responses::ev_assistant_message("verified", "{\"checks\":[{\"verification_id\":\"V01\",\"call_id\":\"verify\",\"acceptance_criteria\":[\"AC01\"]}]}"),
    ].into_iter().enumerate().map(|(index, item)| {
        let id = format!("response-{index}");
        responses::sse(vec![responses::ev_response_created(&id), item, responses::ev_completed_with_tokens(&id, 7)])
    }).collect()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn prepared_survives_process_exit_eof_cannot_approve_and_lock_excludes_competitors()
-> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let prepared = prepare(&fixture, "prepared", "md").await?; // This CLI process has exited.
    let source_events = fs::read(fixture.runs.join("prepared/events.jsonl"))?;
    let eof = timeout(
        Duration::from_secs(45),
        execution(&fixture, &prepared, "eof")?.output(),
    )
    .await??;
    ensure!(!eof.status.success());
    ensure!(
        String::from_utf8_lossy(&eof.stdout).contains("Approval target:"),
        "{}",
        String::from_utf8_lossy(&eof.stderr)
    );
    assert!(server.received_requests().await.unwrap().is_empty());
    let mut host = execution(&fixture, &prepared, "approved")?
        .stdin(Stdio::piped())
        .spawn()?;
    let mut stdout = BufReader::new(host.stdout.take().context("stdout missing")?.take(524288));
    let mut transcript = String::new();
    timeout(Duration::from_secs(45), async {
        loop {
            let mut line = String::new();
            ensure!(
                stdout.read_line(&mut line).await? > 0,
                "execution ended before review"
            );
            let waiting = line.starts_with("Enter approve ");
            transcript.push_str(&line);
            if waiting {
                break;
            }
        }
        anyhow::Ok(())
    })
    .await??;
    assert!(transcript.contains("\"run_id\":\"approved\""));
    assert!(!fixture.repository.join("greeting.txt").exists());
    assert!(server.received_requests().await.unwrap().is_empty());
    let competitor = timeout(
        Duration::from_secs(15),
        execution(&fixture, &prepared, "competitor")?.output(),
    )
    .await??;
    assert!(!competitor.status.success());
    assert!(
        String::from_utf8_lossy(&competitor.stderr)
            .contains("another lab host owns this repository")
    );
    assert!(!fixture.runs.join("competitor").exists());
    let mock = responses::mount_sse_sequence(&server, successful_responses()).await;
    host.stdin
        .take()
        .context("stdin missing")?
        .write_all(format!("approve {}\n", support::plan(1)?.digest()?).as_bytes())
        .await?;
    let (status, _) = timeout(Duration::from_secs(60), async {
        tokio::try_join!(host.wait(), stdout.read_to_string(&mut transcript))
    })
    .await??;
    let mut diagnostic = String::new();
    host.stderr
        .take()
        .context("stderr missing")?
        .take(65536)
        .read_to_string(&mut diagnostic)
        .await?;
    ensure!(status.success(), "execution failed: {diagnostic}");
    assert!(transcript.contains("\"state\": \"completed\""));
    assert_eq!(mock.requests().len(), 5);
    assert_eq!(
        fs::read(fixture.repository.join("greeting.txt"))?,
        b"hello\n"
    );
    assert_eq!(
        fs::read(fixture.runs.join("prepared/events.jsonl"))?,
        source_events
    );
    Ok(())
}

async fn approve_fixture(fixture: &support::Fixture, prepared: &Path, id: &str) -> Result<()> {
    let mut host = execution(fixture, prepared, id)?
        .stdin(Stdio::piped())
        .spawn()?;
    host.stdin
        .take()
        .context("stdin missing")?
        .write_all(format!("approve {}\n", support::plan(1)?.digest()?).as_bytes())
        .await?;
    let output = timeout(Duration::from_secs(45), host.wait_with_output()).await??;
    ensure!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn json_review_wait_does_not_block_an_independent_host_or_accept_its_decision() -> Result<()> {
    let left_server = MockServer::start().await;
    let right_server = MockServer::start().await;
    let left = support::Fixture::new(&left_server.uri()).await?;
    let right = support::Fixture::new(&right_server.uri()).await?;
    let (left_plan, right_plan) = tokio::try_join!(
        prepare(&left, "prepared", "md"), prepare(&right, "prepared", "json"),
    )?;
    let mut left_host = execution(&left, &left_plan, "left")?
        .arg("--review-json").stdin(Stdio::piped()).spawn()?;
    let mut right_host = execution(&right, &right_plan, "right")?
        .arg("--review-json").stdin(Stdio::piped()).spawn()?;
    let mut left_output = BufReader::new(left_host.stdout.take().context("left stdout")?);
    let mut right_output = BufReader::new(right_host.stdout.take().context("right stdout")?);
    let mut left_line = String::new();
    let mut right_line = String::new();
    timeout(Duration::from_secs(45), async {
        tokio::try_join!(left_output.read_line(&mut left_line), right_output.read_line(&mut right_line))
    }).await??;
    let left_request: Value = serde_json::from_str(&left_line)?;
    let right_request: Value = serde_json::from_str(&right_line)?;
    assert_eq!(left_request["type"], "lab_review");
    assert_eq!(right_request["type"], "lab_review");
    let mock = responses::mount_sse_sequence(&right_server, successful_responses()).await;
    let decision = json!({"schema_version":1,"request_id":right_request["request_id"],
        "target":right_request["target"],"command":format!("approve {}",support::plan(1)?.digest()?)});
    right_host.stdin.take().context("right stdin")?
        .write_all(format!("{decision}\n").as_bytes()).await?;
    let mut tail = String::new();
    let (status, _) = timeout(Duration::from_secs(60), async {
        tokio::try_join!(right_host.wait(), right_output.read_to_string(&mut tail))
    }).await??;
    ensure!(status.success(), "independent reviewed host failed");
    assert_eq!(mock.requests().len(), 5);
    assert_eq!(fs::read(right.repository.join("greeting.txt"))?, b"hello\n");
    assert!(left_host.try_wait()?.is_none());
    assert!(!left.repository.join("greeting.txt").exists());
    assert!(left_server.received_requests().await.unwrap().is_empty());
    // Identical canonical digest is insufficient: the response belongs to right.
    left_host.stdin.take().context("left stdin")?
        .write_all(format!("{decision}\n").as_bytes()).await?;
    let output = timeout(Duration::from_secs(20), left_host.wait_with_output()).await??;
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("does not match current request and target"));
    assert!(left_server.received_requests().await.unwrap().is_empty());
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn prepared_completed_cli_pair_compares_only_renderer() -> Result<()> {
    let server = MockServer::start().await;
    let fixture = support::Fixture::new(&server.uri()).await?;
    let prepared = prepare(&fixture, "prepared", "md").await?;
    let mock = responses::mount_sse_sequence(&server, successful_responses()).await;
    approve_fixture(&fixture, &prepared, "approved").await?;
    assert_eq!(mock.requests().len(), 5);
    // A second condition consumes the same canonical plan with JSON rendering.
    // Synthetic evaluator records test the comparison adapter, not task quality.
    fs::remove_file(fixture.repository.join("greeting.txt"))?;
    let prepared_json = prepare(&fixture, "prepared-json", "json").await?;
    let mock_json = responses::mount_sse_sequence(&server, successful_responses()).await;
    approve_fixture(&fixture, &prepared_json, "approved-json").await?;
    assert_eq!(mock_json.requests().len(), 5);
    for id in ["approved", "approved-json"] {
        use sha2::Digest;
        let run = fixture.runs.join(id);
        let spec: Value = serde_json::from_slice(&fs::read(run.join("config/run-spec.json"))?)?;
        let task_sha256 = format!(
            "{:x}",
            sha2::Sha256::digest(spec["task"].as_str().unwrap().as_bytes())
        );
        fs::create_dir(run.join("evaluation"))?;
        fs::write(
            run.join("evaluation/evaluation.json"),
            serde_json::to_vec(&json!({
                "schema_version":1,"run":run,"fixture":"mock-greeting","fixture_commit":fixture.commit,
                "task_sha256":task_sha256,"python":{"version":"test-only"},"evaluator_sha256":"test-only",
                "sandbox_sha256":"test-only","task_success":true,"hidden_test_success":true,"public_test_success":true
            }))?,
        )?;
    }
    let report_path = codex_lab_runtime::compare_runs(
        &fixture.runs.join("approved"),
        &fixture.runs.join("approved-json"),
        "plan.renderer",
        &fixture.runs.join("comparison"),
    )?;
    let report: Value = serde_json::from_slice(&fs::read(report_path)?)?;
    assert_eq!(
        report["classification"],
        "controlled_recorded_pair",
        "{}",
        serde_json::to_string_pretty(&report)?
    );
    assert_eq!(
        report["control_differences"],
        json!([{"path":"plan.renderer","left":"markdown","right":"json"}])
    );
    Ok(())
}
