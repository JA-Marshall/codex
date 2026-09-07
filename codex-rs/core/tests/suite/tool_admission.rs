use std::fs;
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::AtomicBool;
use std::sync::atomic::AtomicUsize;
use std::sync::atomic::Ordering;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use codex_core::TurnInputRequest;
use codex_core::config::Config;
use codex_extension_api::ExtensionFuture;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_extension_api::ToolAdmissionContributor;
use codex_extension_api::ToolAdmissionError;
use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolAdmissionPermit;
use codex_extension_api::ToolCallOutcome;
use codex_extension_api::ToolCallSource;
use codex_extension_api::ToolFinishInput;
use codex_extension_api::ToolLifecycleContributor;
use codex_extension_api::ToolLifecycleFuture;
use codex_extension_api::ToolStartInput;
use codex_features::Feature;
use codex_protocol::protocol::EventMsg;
use codex_protocol::protocol::Op;
use codex_protocol::user_input::UserInput;
use core_test_support::hooks::trust_discovered_hooks;
use core_test_support::responses;
use core_test_support::skip_if_no_network;
use core_test_support::skip_if_wine_exec;
use core_test_support::test_codex::test_codex;
use core_test_support::wait_for_event;
use pretty_assertions::assert_eq;
use serde_json::json;
use tokio::sync::Notify;
use tokio::time::timeout;

#[derive(Default)]
struct AdmissionPolicy {
    open: AtomicBool,
    denied_tool: Option<&'static str>,
    active: Arc<AtomicUsize>,
    calls: Mutex<Vec<(String, ToolCallSource)>>,
    outcomes: Mutex<Vec<ToolCallOutcome>>,
    started: Notify,
    block_start: bool,
}

struct ActiveCall(Arc<AtomicUsize>);

impl Drop for ActiveCall {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

impl ToolAdmissionContributor for AdmissionPolicy {
    fn admit<'a>(
        &'a self,
        input: ToolAdmissionInput<'a>,
    ) -> ExtensionFuture<'a, Result<ToolAdmissionPermit, ToolAdmissionError>> {
        Box::pin(async move {
            self.calls
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .push((input.tool_name.name.clone(), input.source));
            if !self.open.load(Ordering::SeqCst)
                && self
                    .denied_tool
                    .is_none_or(|name| input.tool_name.name == name)
            {
                return Err(ToolAdmissionError::new("exact plan approval required"));
            }
            self.active.fetch_add(1, Ordering::SeqCst);
            Ok(ToolAdmissionPermit::new(ActiveCall(Arc::clone(
                &self.active,
            ))))
        })
    }
}

impl ToolLifecycleContributor for AdmissionPolicy {
    fn on_tool_start<'a>(&'a self, _input: ToolStartInput<'a>) -> ToolLifecycleFuture<'a> {
        Box::pin(async move {
            self.started.notify_one();
            if self.block_start {
                std::future::pending::<()>().await;
            }
        })
    }

    fn on_tool_finish<'a>(&'a self, input: ToolFinishInput<'a>) -> ToolLifecycleFuture<'a> {
        Box::pin(async move {
            self.outcomes
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .push(input.outcome);
        })
    }
}

fn registry(policy: &Arc<AdmissionPolicy>) -> Arc<codex_extension_api::ExtensionRegistry<Config>> {
    let mut builder = ExtensionRegistryBuilder::<Config>::new();
    builder.tool_admission_contributor(policy.clone());
    builder.tool_lifecycle_contributor(policy.clone());
    Arc::new(builder.build())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn admission_blocks_workspace_mutation_until_host_authorizes_it() -> Result<()> {
    skip_if_no_network!(Ok(()));
    let server = responses::start_mock_server().await;
    let policy = Arc::new(AdmissionPolicy::default());
    let test = test_codex()
        .with_extensions(registry(&policy))
        .build_with_auto_env(&server)
        .await?;
    for expected_open in [false, true] {
        let call_id = if expected_open {
            "approved-write"
        } else {
            "blocked-write"
        };
        responses::mount_sse_once(
            &server,
            responses::sse(vec![
                responses::ev_function_call(
                    call_id,
                    "exec_command",
                    &json!({"cmd": "echo admitted > admission.txt", "login": false}).to_string(),
                ),
                responses::ev_completed("tool-response"),
            ]),
        )
        .await;
        let follow_up = responses::mount_sse_once(
            &server,
            responses::sse(vec![responses::ev_completed("final-response")]),
        )
        .await;
        policy.open.store(expected_open, Ordering::SeqCst);
        test.submit_turn("Write the file.").await?;
        let contents = test
            .fs()
            .read_file(
                &test.workspace_path_uri("admission.txt")?,
                Default::default(),
                /*sandbox*/ None,
            )
            .await;
        if expected_open {
            assert!(!contents?.is_empty());
        } else {
            assert!(contents.is_err());
            let output = follow_up.single_request().function_call_output(call_id);
            insta::assert_snapshot!(output["output"].as_str().context("tool output must be text")?, @"Tool blocked by host admission policy: exact plan approval required");
        }
        assert_eq!(policy.active.load(Ordering::SeqCst), 0);
    }
    assert_eq!(
        *policy
            .outcomes
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner),
        [
            ToolCallOutcome::Blocked,
            ToolCallOutcome::Completed { success: true }
        ]
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn admission_denial_precedes_pre_tool_hook_side_effects() -> Result<()> {
    skip_if_no_network!(Ok(()));
    skip_if_wine_exec!(Ok(()), "command hooks require a host-native executor");
    let server = responses::start_mock_server().await;
    let home = Arc::new(tempfile::tempdir()?);
    let script = home.path().join("admission_hook.py");
    fs::write(
        &script,
        "from pathlib import Path\nPath(__file__).with_suffix('.ran').write_text('ran')\nprint('{}')\n",
    )?;
    fs::write(
        home.path().join("hooks.json"),
        json!({"hooks": {
            "PreToolUse": [{"matcher": "^update_plan$", "hooks": [{
                "type": "command", "command": format!("python3 \"{}\"", script.display())
            }]}]
        }})
        .to_string(),
    )?;
    let policy = Arc::new(AdmissionPolicy::default());
    let test = test_codex()
        .with_home(home)
        .with_extensions(registry(&policy))
        .with_config(trust_discovered_hooks)
        .with_config(|config| config.update_plan_enabled = true)
        .build_with_auto_env(&server)
        .await?;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_function_call(
                "plan-call",
                "update_plan",
                r#"{"plan":[{"step":"step","status":"in_progress"}]}"#,
            ),
            responses::ev_completed("tool-response"),
        ]),
    )
    .await;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![responses::ev_completed("final-response")]),
    )
    .await;
    test.submit_text_turn("Update the plan.").await?;
    assert!(!script.with_extension("ran").exists());
    policy.open.store(true, Ordering::SeqCst);
    responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_function_call(
                "approved-plan-call",
                "update_plan",
                r#"{"plan":[{"step":"step","status":"in_progress"}]}"#,
            ),
            responses::ev_completed("approved-tool-response"),
        ]),
    )
    .await;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![responses::ev_completed("approved-final-response")]),
    )
    .await;
    test.submit_text_turn("Update the plan after admission.")
        .await?;
    assert_eq!(fs::read_to_string(script.with_extension("ran"))?, "ran");
    assert_eq!(
        *policy
            .outcomes
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner),
        [
            ToolCallOutcome::Blocked,
            ToolCallOutcome::Completed { success: true }
        ]
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn code_mode_nested_tools_must_obtain_their_own_admission() -> Result<()> {
    skip_if_no_network!(Ok(()));
    let server = responses::start_mock_server().await;
    let policy = Arc::new(AdmissionPolicy {
        denied_tool: Some("update_plan"),
        ..Default::default()
    });
    let test = test_codex()
        .with_extensions(registry(&policy))
        .with_config(|config| {
            let _ = config.features.enable(Feature::CodeMode);
            config.update_plan_enabled = true;
        })
        .build_with_auto_env(&server)
        .await?;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_custom_tool_call(
                "exec-call",
                "exec",
                r#"text(await tools.update_plan({plan:[{step:"step",status:"in_progress"}]}));"#,
            ),
            responses::ev_completed("tool-response"),
        ]),
    )
    .await;
    let follow_up = responses::mount_sse_once(
        &server,
        responses::sse(vec![responses::ev_completed("final-response")]),
    )
    .await;
    test.submit_text_turn("Call update_plan from code mode.")
        .await?;
    let calls = policy
        .calls
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    assert!(
        calls
            .iter()
            .any(|(name, source)| name == "exec" && matches!(source, ToolCallSource::Direct))
    );
    assert!(
        calls.iter().any(|(name, source)| name == "update_plan"
            && matches!(source, ToolCallSource::CodeMode { .. }))
    );
    assert!(
        follow_up
            .single_request()
            .custom_tool_call_output("exec-call")["output"]
            .to_string()
            .contains("exact plan approval required")
    );
    assert_eq!(policy.active.load(Ordering::SeqCst), 0);
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn handler_failure_releases_admission_permits() -> Result<()> {
    skip_if_no_network!(Ok(()));
    let server = responses::start_mock_server().await;
    let policy = Arc::new(AdmissionPolicy {
        open: AtomicBool::new(true),
        ..Default::default()
    });
    let test = test_codex()
        .with_extensions(registry(&policy))
        .with_config(|config| config.update_plan_enabled = true)
        .build_with_auto_env(&server)
        .await?;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_function_call("invalid-plan-call", "update_plan", "{}"),
            responses::ev_completed("tool-response"),
        ]),
    )
    .await;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![responses::ev_completed("final-response")]),
    )
    .await;
    test.submit_text_turn("Call the tool with invalid arguments.")
        .await?;
    assert_eq!(policy.active.load(Ordering::SeqCst), 0);
    assert_eq!(
        *policy
            .outcomes
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner),
        [ToolCallOutcome::Failed {
            handler_executed: true
        }]
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn interrupt_releases_admission_permits_while_dispatch_is_pending() -> Result<()> {
    skip_if_no_network!(Ok(()));
    let server = responses::start_mock_server().await;
    let policy = Arc::new(AdmissionPolicy {
        open: AtomicBool::new(true),
        block_start: true,
        ..Default::default()
    });
    let test = test_codex()
        .with_extensions(registry(&policy))
        .with_config(|config| config.update_plan_enabled = true)
        .build_with_auto_env(&server)
        .await?;
    responses::mount_sse_once(
        &server,
        responses::sse(vec![
            responses::ev_function_call(
                "plan-call",
                "update_plan",
                r#"{"plan":[{"step":"step","status":"in_progress"}]}"#,
            ),
            responses::ev_completed("tool-response"),
        ]),
    )
    .await;
    test.codex
        .start_or_steer_turn(TurnInputRequest::user_input(vec![UserInput::Text {
            text: "Start the tool.".to_string(),
            text_elements: Vec::new(),
        }]))
        .await?;
    timeout(Duration::from_secs(30), policy.started.notified()).await?;
    assert_eq!(policy.active.load(Ordering::SeqCst), 1);
    test.codex.submit(Op::Interrupt).await?;
    wait_for_event(&test.codex, |event| {
        matches!(event, EventMsg::TurnAborted(_))
    })
    .await;
    assert_eq!(policy.active.load(Ordering::SeqCst), 0);
    Ok(())
}
