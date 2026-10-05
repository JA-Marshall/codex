//! Opt-in offline startup smoke for externally supplied, frozen pilot tasks.
//!
//! This validates permissions, dependency access and lifecycle plumbing, not
//! whether the benchmark tasks have been solved. All edits target fresh copies.

#![cfg(target_os = "linux")]

#[path = "support/runtime.rs"]
mod support;

use std::collections::BTreeMap;
use std::path::Path;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use core_test_support::responses;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;
use sha2::Digest;
use tokio::process::Command;
use tokio::time::timeout;
use wiremock::MockServer;

const SETUP: &str = r#"
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from task_registry import load_task, setup
print(json.dumps(setup(pathlib.Path(sys.argv[3]), load_task(pathlib.Path(sys.argv[2])))))
"#;

const PROBE: &str = r#"
import errno, os, pathlib, runpy, sys
import pydantic
assert pydantic.__version__ == '2.13.4'
target, private, sibling, mode = map(pathlib.Path, sys.argv[1:])
mode = str(mode)
sys.path.insert(0, str(pathlib.Path.cwd() / 'src'))
runpy.run_path(str(target))
for forbidden in (private, sibling):
    try:
        with forbidden.open('rb') as stream:
            stream.read(1)
    except OSError as error:
        assert error.errno in (errno.EACCES, errno.EPERM, errno.ENOENT), error
    else:
        raise AssertionError('private sibling became readable')
marker = pathlib.Path('tests/startup_probe_marker.txt')
suffix = b'\n# Offline startup permission probe.\n'
if mode == 'implement':
    target.write_bytes(target.read_bytes() + suffix)
    marker.write_text('startup-only\n')
else:
    assert mode == 'verify'
    assert target.read_bytes().endswith(suffix)
    assert marker.read_text() == 'startup-only\n'
for forbidden in (target.with_name('unapproved_sibling.py'), pathlib.Path('TASK.md'),
                  pathlib.Path('tests/AGENTS.md')) + (() if mode == 'implement' else (target, marker)):
    try:
        with forbidden.open('ab'):
            pass
    except OSError as error:
        assert error.errno in (errno.EACCES, errno.EPERM, errno.EROFS), error
    else:
        raise AssertionError('write outside phase scope succeeded')
assert not os.access(pydantic.__file__, os.W_OK)
print('startup-permissions-runtime-ok')
"#;

fn required_path(name: &str) -> Result<PathBuf> {
    PathBuf::from(std::env::var_os(name).with_context(|| format!("set {name}"))?)
        .canonicalize()
        .with_context(|| format!("resolve {name}"))
}

fn inventory(root: &Path) -> Result<BTreeMap<PathBuf, String>> {
    let mut pending = vec![root.to_path_buf()];
    let mut files = BTreeMap::new();
    while let Some(directory) = pending.pop() {
        for entry in std::fs::read_dir(directory)? {
            let path = entry?.path();
            let metadata = std::fs::symlink_metadata(&path)?;
            ensure!(!metadata.is_symlink(), "linked task asset");
            if metadata.is_dir() {
                pending.push(path);
            } else {
                ensure!(metadata.is_file(), "unsupported task asset");
                files.insert(
                    path.strip_prefix(root)?.to_path_buf(),
                    format!("{:x}", sha2::Sha256::digest(std::fs::read(path)?)),
                );
            }
        }
    }
    Ok(files)
}

fn quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn response(id: &str, item: Value) -> String {
    responses::sse(vec![
        responses::ev_response_created(id),
        item,
        responses::ev_completed_with_tokens(id, 7),
    ])
}

fn exec(id: &str, command: &str) -> String {
    response(
        id,
        responses::ev_function_call(
            id,
            "exec_command",
            &json!({
                "cmd": command, "max_output_tokens": 2048, "timeout_ms": 10000
            })
            .to_string(),
        ),
    )
}

/// Run explicitly with CODEX_LAB_PILOT_TASK_ROOT, CODEX_LAB_PILOT_PYTHON and
/// CODEX_LAB_PILOT_BINARY. Set CODEX_LAB_PILOT_EXPECT_SCOPE_FAILURE=1 only when
/// reproducing the old file-scope bug. CODEX_LAB_PILOT_EXPORT is a new directory.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "requires frozen pilot assets and standalone Python with pinned Pydantic"]
async fn actual_pilot_tasks_complete_offline_startup_with_file_scopes() -> Result<()> {
    let tasks = required_path("CODEX_LAB_PILOT_TASK_ROOT")?;
    let python = required_path("CODEX_LAB_PILOT_PYTHON")?;
    let binary = required_path("CODEX_LAB_PILOT_BINARY")?;
    let runtime = python
        .parent()
        .and_then(Path::parent)
        .context("standalone Python root")?;
    let expected_failure =
        std::env::var("CODEX_LAB_PILOT_EXPECT_SCOPE_FAILURE").as_deref() == Ok("1");
    let export = std::env::var_os("CODEX_LAB_PILOT_EXPORT").map(PathBuf::from);
    if let Some(path) = &export {
        ensure!(
            path.is_absolute() && !path.exists(),
            "export must be a new absolute directory"
        );
        ensure!(
            !path.starts_with(&tasks) && !path.starts_with(runtime),
            "export overlaps frozen inputs"
        );
        std::fs::create_dir_all(path)?;
    }
    let binary_sha256 = format!("{:x}", sha2::Sha256::digest(std::fs::read(&binary)?));
    let mut outcomes = Vec::new();
    for (name, target) in [
        ("py-phmt-serial-hardening", "src/validate_phmt_serial.py"),
        (
            "py-supermicro-coordinator",
            "src/supermicro_lab/jobs/coordinator.py",
        ),
    ] {
        let source = tasks.join(name);
        let before = inventory(&source)?;
        let manifest: Value =
            serde_json::from_slice(&std::fs::read(source.join("manifest.json"))?)?;
        assert_eq!(manifest["write_paths"], json!([target, "tests"]));
        let server = MockServer::start().await;
        ensure!(
            server.address().ip().is_loopback(),
            "mock provider must be loopback-only"
        );
        let mut fixture = support::Fixture::new(&server.uri()).await?;
        let destination = fixture
            .runs
            .parent()
            .context("fixture parent")?
            .join("actual-task");
        let setup = Command::new(&python)
            .args(["-I", "-B", "-c", SETUP])
            .arg(
                tasks
                    .parent()
                    .context("task library parent")?
                    .join("experiments"),
            )
            .arg(&source)
            .arg(&destination)
            .stdin(Stdio::null())
            .output()
            .await?;
        ensure!(
            setup.status.success(),
            "copy actual task: {}",
            String::from_utf8_lossy(&setup.stderr)
        );
        let metadata: Value = serde_json::from_slice(&setup.stdout)?;
        fixture.repository = PathBuf::from(
            metadata["repository"]
                .as_str()
                .context("copied repository")?,
        );
        fixture.commit = metadata["commit"]
            .as_str()
            .context("copied commit")?
            .to_owned();
        let task = std::fs::read_to_string(fixture.repository.join("TASK.md"))?;
        ensure!(
            task.contains(python.to_str().context("Python path UTF-8")?),
            "task lacks exact interpreter instruction"
        );
        let sibling = fixture
            .repository
            .parent()
            .context("repository parent")?
            .join("private-sibling.txt");
        std::fs::write(&sibling, "sibling must stay private")?;
        ensure!(
            source.join("private/cases.json").is_file() && sibling.is_file(),
            "private probe files must exist on the host"
        );
        let command = [
            &python.to_string_lossy(),
            "-I",
            "-B",
            "-c",
            PROBE,
            target,
            &source.join("private/cases.json").to_string_lossy(),
            &sibling.to_string_lossy(),
        ]
        .into_iter()
        .map(quote)
        .collect::<Vec<_>>()
        .join(" ");
        let plan = json!({
            "schema_version":1,"plan_id":"task-plan","revision":1,
            "goal":"Validate startup, permissions, dependency access and shutdown only; not task correctness.",
            "assumptions":["Work only in this copied task and use its pinned Python interpreter."],
            "risks":[],"discoveries":[],"blockers":[],
            "acceptance_criteria":[{"id":"AC01","description":"Exact file and test writes work only during implementation, private reads fail and runtime imports succeed."}],
            "verification_strategy":[{"id":"V01","description":"Run the read-only startup probe and cite its completed host command."}],
            "steps":[{"id":"S01","title":"Exercise offline startup permissions","instructions":"Append a harmless comment to the allowed source file and create the test marker, then verify runtime imports and denied accesses.",
                "affected_files":[target,"tests/startup_probe_marker.txt"],"depends_on":[],"acceptance_criteria":["AC01"],"verification":["V01"]}]
        });
        let mock = if expected_failure {
            None
        } else {
            Some(responses::mount_sse_sequence(&server, vec![
            response("research", responses::ev_assistant_message("research", "Offline startup smoke uses the supplied exact file scope and interpreter.")),
            response("plan", responses::ev_assistant_message("plan", &plan.to_string())),
            exec("implement-startup", &format!("{command} implement")),
            response("implementation", responses::ev_assistant_message("implementation", r#"{"completed_steps":["S01"]}"#)),
            exec("verify-startup", &format!("{command} verify")),
            response("receipt", responses::ev_function_call("receipt", "lab_command_receipt", r#"{"index":1}"#)),
            response("verification", responses::ev_assistant_message("verification", r#"{"checks":[{"verification_id":"V01","call_id":"verify-startup","acceptance_criteria":["AC01"]}]}"#)),
        ]).await)
        };
        let catalog = fixture
            .workflow_catalog
            .replace("human_required", "campaign_delegated");
        let catalog_path = fixture.home.join("workflow.toml");
        std::fs::write(&catalog_path, &catalog)?;
        let policy = json!({
            "schema_version":1,"campaign_id":"offline-startup-smoke","run_id":"startup",
            "repository":fixture.repository,"repository_commit":fixture.commit,
            "task_sha256":format!("{:x}",sha2::Sha256::digest(task.as_bytes())),
            "workflow":"md","workflow_catalog_sha256":format!("{:x}",sha2::Sha256::digest(catalog.as_bytes())),
            "max_amendments":0,"task_scope":{"schema_version":1,"write_paths":manifest["write_paths"],
                "read_paths":[runtime],"deny_read_paths":[tasks]}
        });
        let policy_path = fixture.home.join("policy.json");
        std::fs::write(&policy_path, serde_json::to_vec(&policy)?)?;
        let output = timeout(
            Duration::from_secs(120),
            Command::new(&binary)
                .env_clear()
                .env("PATH", "/usr/local/bin:/usr/bin:/bin")
                .env("HOME", &fixture.home)
                .env("CODEX_HOME", &fixture.home)
                .env("LANG", "C.UTF-8")
                .env("PYTHONNOUSERSITE", "1")
                .env("PYTHONDONTWRITEBYTECODE", "1")
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
                .args(["--run-id", "startup", "--workflow", "md"])
                .arg("--task-file")
                .arg(fixture.repository.join("TASK.md"))
                .arg("--workflow-catalog")
                .arg(&catalog_path)
                .arg("--instruction-root")
                .arg(&fixture.instruction_root)
                .arg("--campaign-policy")
                .arg(&policy_path)
                .stdin(Stdio::null())
                .kill_on_drop(true)
                .output(),
        )
        .await??;
        let artifacts = fixture.runs.join("startup");
        if let Some(path) = &export {
            let copy = Command::new("cp")
                .arg("-a")
                .arg(&artifacts)
                .arg(path.join(name))
                .status()
                .await?;
            ensure!(copy.success(), "export smoke artifacts");
            std::fs::write(path.join(format!("{name}.stdout.log")), &output.stdout)?;
            std::fs::write(path.join(format!("{name}.stderr.log")), &output.stderr)?;
        }
        assert_eq!(inventory(&source)?, before, "frozen task assets changed");
        let requests = mock
            .as_ref()
            .map(core_test_support::responses::ResponseMock::requests)
            .unwrap_or_default();
        let request_count = server
            .received_requests()
            .await
            .context("mock request recording")?
            .len();
        // Check request counts explicitly below so teardown cannot obscure a CLI failure.
        server.reset().await;
        let events = std::fs::read_to_string(artifacts.join("runtime-events.jsonl"))?
            .lines()
            .map(serde_json::from_str::<Value>)
            .collect::<serde_json::Result<Vec<_>>>()?;
        let phase_starts = events
            .iter()
            .filter(|event| event["type"] == "phase_started")
            .count();
        if expected_failure {
            ensure!(
                !output.status.success(),
                "old binary unexpectedly passed startup"
            );
            let failure: Value =
                serde_json::from_slice(&std::fs::read(artifacts.join("evidence/failure.json"))?)?;
            assert_eq!(failure["classification"], "scope_blocked");
            ensure!(
                failure["error"]
                    .as_str()
                    .context("scope error")?
                    .contains("Not a directory"),
                "unexpected old-binary failure: {failure}"
            );
            assert_eq!((phase_starts, request_count), (0, 0));
        } else {
            ensure!(
                output.status.success(),
                "actual task {name} startup failed: {}",
                String::from_utf8_lossy(&output.stderr)
            );
            let result: Value = serde_json::from_slice(&output.stdout)?;
            assert_eq!(
                (result["state"].clone(), phase_starts, request_count),
                (json!("completed"), 4, 7)
            );
            let request = requests.last().context("final mock request")?;
            for id in ["implement-startup", "verify-startup"] {
                let text = requests
                    .iter()
                    .find_map(|request| request.function_call_output_text(id))
                    .with_context(|| format!("missing {id} output"))?;
                ensure!(
                    text.contains("startup-permissions-runtime-ok")
                        && text.contains("Process exited with code 0"),
                    "probe did not succeed: {text}"
                );
            }
            let receipt: Value = serde_json::from_str(
                &request
                    .function_call_output_text("receipt")
                    .context("host command receipt")?,
            )?;
            assert_eq!(receipt["receipt"]["call_id"], "verify-startup");
            for index in 1..=4 {
                let phase: Value = serde_json::from_slice(&std::fs::read(
                    artifacts.join(format!("evidence/phase-{index:02}.json")),
                )?)?;
                assert_eq!(phase["task_scope"]["audit"]["authorized"], true);
                ensure!(
                    phase["events"]
                        .as_array()
                        .context("phase events")?
                        .iter()
                        .any(|event| event["msg"]["type"] == "shutdown_complete"),
                    "phase lacks shutdown proof"
                );
                if index != 3 {
                    assert_eq!(phase["task_scope"]["candidate_write_paths"], json!([]));
                    assert_eq!(phase["task_scope"]["audit"]["candidate_unchanged"], true);
                }
            }
        }
        outcomes.push(
            json!({"task":name,"expected_original_scope_failure":expected_failure,
            "phase_starts":phase_starts,"local_mock_requests":request_count,
            "external_model_requests":0,"source_assets_unchanged":true}),
        );
    }
    let summary = json!({"purpose":"permissions-runtime-lifecycle-only; not task solution correctness",
        "binary":binary,"binary_sha256":binary_sha256,"python":python,"runtime":runtime,
        "task_root":tasks,"outcomes":outcomes});
    eprintln!("{}", serde_json::to_string_pretty(&summary)?);
    if let Some(path) = export {
        std::fs::write(
            path.join("startup-smoke.json"),
            serde_json::to_vec_pretty(&summary)?,
        )?;
    }
    Ok(())
}
