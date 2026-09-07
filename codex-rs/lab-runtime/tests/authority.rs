mod authority_support;

use std::fs;

use anyhow::Context;
use anyhow::Result;
use codex_extension_api::ExtensionData;
use codex_extension_api::ToolAdmissionContributor;
use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolCallOutcome;
use codex_extension_api::ToolCallSource;
use codex_extension_api::ToolFinishInput;
use codex_extension_api::ToolLifecycleContributor;
use codex_extension_api::ToolName;
use codex_lab::LabRun;
use codex_lab::WorkflowState;
use codex_lab_runtime::Phase;
use codex_lab_runtime::RunAuthority;
use pretty_assertions::assert_eq;
use serde_json::Value;
use serde_json::json;

fn input<'a>(
    store: &'a ExtensionData,
    name: &'a ToolName,
    thread: &'a str,
) -> ToolAdmissionInput<'a> {
    ToolAdmissionInput {
        session_store: store,
        thread_store: store,
        turn_store: store,
        thread_id: thread,
        turn_id: "turn",
        call_id: "call",
        tool_name: name,
        source: ToolCallSource::Direct,
    }
}

#[tokio::test]
async fn phase_requires_the_bound_thread_and_explicit_tool_capability() -> Result<()> {
    let (_root, run) = authority_support::new_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Research)?;
    let store = ExtensionData::new("thread");
    let read = ToolName::plain("lab_repo_read");
    assert!(gate.admit(input(&store, &read, "thread")).await.is_err());
    gate.bind_thread("thread")?;
    assert!(gate.bind_thread("thread").is_err());
    assert!(gate.admit(input(&store, &read, "child")).await.is_err());
    drop(gate.admit(input(&store, &read, "thread")).await?);
    let shell = ToolName::plain("exec_command");
    assert!(gate.admit(input(&store, &shell, "thread")).await.is_err());
    assert!(
        gate.admit(input(
            &store,
            &ToolName::plain("lab_command_receipt"),
            "thread"
        ))
        .await
        .is_err()
    );
    let foreign = ToolName::namespaced("mcp__remote", "lab_repo_read");
    assert!(gate.admit(input(&store, &foreign, "thread")).await.is_err());
    let mut nested = input(&store, &read, "thread");
    nested.source = ToolCallSource::CodeMode {
        cell_id: "cell".into(),
        runtime_tool_call_id: "nested".into(),
    };
    assert!(gate.admit(nested).await.is_err());
    Ok(())
}

#[tokio::test]
async fn host_transitions_and_new_phases_wait_for_dispatch_accounting() -> Result<()> {
    let (_root, run) = authority_support::new_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Research)?;
    gate.bind_thread("thread")?;
    let store = ExtensionData::new("thread");
    let read = ToolName::plain("lab_repo_read");
    let permit = gate.admit(input(&store, &read, "thread")).await?;
    assert!(authority.update(LabRun::begin_planning).is_err());
    assert!(authority.start_phase(Phase::Planning).is_err());
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    drop(permit);
    assert_eq!(authority.finish_phase_after_shutdown(&gate)?, None);
    authority.update(LabRun::begin_planning)?;
    let next = authority.start_phase(Phase::Planning)?;
    next.bind_thread("next-thread")?;
    assert!(gate.admit(input(&store, &read, "thread")).await.is_err());
    assert!(gate.bind_thread("other-thread").is_err());
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    drop(next.admit(input(&store, &read, "next-thread")).await?);
    Ok(())
}

#[tokio::test]
async fn amendment_revokes_immediately_and_requires_a_new_exact_approval_after_shutdown()
-> Result<()> {
    let (_root, run) = authority_support::approved_run()?;
    let authority = RunAuthority::new(run)?;
    let old_target = authority.snapshot()?.approved.context("approved target")?;
    let gate = authority.start_phase(Phase::Implementation)?;
    gate.bind_thread("thread")?;
    let store = ExtensionData::new("thread");
    let shell = ToolName::plain("exec_command");
    let permit = gate.admit(input(&store, &shell, "thread")).await?;
    assert!(
        gate.admit(input(
            &store,
            &ToolName::plain("lab_command_receipt"),
            "thread"
        ))
        .await
        .is_err()
    );
    gate.request_amendment("An assumption was invalid")?;
    assert!(gate.cancellation().is_cancelled());
    assert_eq!(authority.snapshot()?.state, WorkflowState::Implementing);
    assert!(gate.admit(input(&store, &shell, "thread")).await.is_err());
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    drop(permit);
    assert_eq!(
        authority.finish_phase_after_shutdown(&gate)?,
        Some("An assumption was invalid".into())
    );
    assert_eq!(
        authority.snapshot()?.state,
        WorkflowState::AwaitingPlanAmendment
    );
    assert_eq!(authority.snapshot()?.approved, None);
    let planner = authority.start_phase(Phase::Planning)?;
    planner.bind_thread("amendment-thread")?;
    let read = ToolName::plain("lab_repo_read");
    drop(
        planner
            .admit(input(&store, &read, "amendment-thread"))
            .await?,
    );
    assert!(
        planner
            .admit(input(&store, &shell, "amendment-thread"))
            .await
            .is_err()
    );
    authority.finish_phase_after_shutdown(&planner)?;
    let revised = authority_support::plan(2)?;
    authority.update(|run| run.submit_plan(revised))?;
    assert!(authority.start_phase(Phase::Implementation).is_err());
    assert!(
        authority
            .update(|run| run.approve(old_target, "human"))
            .is_err()
    );
    let new_target = authority.snapshot()?.target.context("amended target")?;
    authority.update(|run| run.approve(new_target, "human"))?;
    let executor = authority.start_phase(Phase::Implementation)?;
    executor.bind_thread("new-thread")?;
    assert!(gate.admit(input(&store, &shell, "thread")).await.is_err());
    drop(executor.admit(input(&store, &shell, "new-thread")).await?);
    Ok(())
}

#[tokio::test]
async fn dropping_a_cancelled_dispatch_releases_the_phase_lease() -> Result<()> {
    let (_root, run) = authority_support::approved_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Implementation)?;
    gate.bind_thread("thread")?;
    let store = ExtensionData::new("thread");
    let shell = ToolName::plain("exec_command");
    let permit = gate.admit(input(&store, &shell, "thread")).await?;
    let mut dispatch = Box::pin(async move {
        let _permit = permit;
        std::future::pending::<()>().await;
    });
    assert!(
        std::future::poll_fn(|context| std::task::Poll::Ready(dispatch.as_mut().poll(context)))
            .await
            .is_pending()
    );
    gate.request_amendment("Stop the running work")?;
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    drop(dispatch);
    assert_eq!(
        authority.finish_phase_after_shutdown(&gate)?,
        Some("Stop the running work".into())
    );
    Ok(())
}

#[tokio::test]
async fn runtime_journal_records_structured_outcomes_and_monotonic_time() -> Result<()> {
    let (_root, run) = authority_support::new_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Research)?;
    gate.bind_thread("thread")?;
    let store = ExtensionData::new("thread");
    let read = ToolName::plain("lab_repo_read");
    let permit = gate.admit(input(&store, &read, "thread")).await?;
    let unrelated_thread = ExtensionData::new("other-thread");
    gate.on_tool_finish(ToolFinishInput {
        session_store: &store,
        thread_store: &unrelated_thread,
        turn_store: &store,
        turn_id: "turn",
        call_id: "call",
        tool_name: &read,
        source: ToolCallSource::Direct,
        outcome: ToolCallOutcome::Blocked,
    })
    .await;
    gate.on_tool_finish(ToolFinishInput {
        session_store: &store,
        thread_store: &store,
        turn_store: &store,
        turn_id: "turn",
        call_id: "call",
        tool_name: &read,
        source: ToolCallSource::Direct,
        outcome: ToolCallOutcome::Completed { success: true },
    })
    .await;
    drop(permit);
    authority.finish_phase_after_shutdown(&gate)?;
    let events = fs::read_to_string(authority.artifacts()?.join("runtime-events.jsonl"))?
        .lines()
        .map(serde_json::from_str)
        .collect::<Result<Vec<Value>, _>>()?;
    assert_eq!(
        events
            .iter()
            .map(|event| event["type"].clone())
            .collect::<Vec<_>>(),
        [
            json!("phase_started"),
            json!("phase_thread_bound"),
            json!("tool_admitted"),
            json!("tool_finished"),
            json!("phase_stopped")
        ]
    );
    assert_eq!(
        events[3]["outcome"],
        json!({"type":"completed", "success":true})
    );
    for (index, event) in events.iter().enumerate() {
        assert_eq!(event["sequence"], json!(index + 1));
        assert!(event["unix_ms"].as_u64().is_some());
        assert!(event["elapsed_ms"].as_u64().is_some());
    }
    assert!(
        events
            .windows(2)
            .all(|pair| pair[0]["elapsed_ms"].as_u64() <= pair[1]["elapsed_ms"].as_u64())
    );
    Ok(())
}

#[test]
fn shutdown_acknowledgement_cannot_target_another_run_with_the_same_epoch() -> Result<()> {
    let (_first_root, first_run) = authority_support::new_run()?;
    let (_second_root, second_run) = authority_support::new_run()?;
    let first = RunAuthority::new(first_run)?;
    let second = RunAuthority::new(second_run)?;
    let first_gate = first.start_phase(Phase::Research)?;
    let second_gate = second.start_phase(Phase::Research)?;
    assert!(first.finish_phase_after_shutdown(&second_gate).is_err());
    assert_eq!(first.finish_phase_after_shutdown(&first_gate)?, None);
    Ok(())
}

#[tokio::test]
async fn host_failure_revokes_an_active_phase_without_claiming_shutdown() -> Result<()> {
    let (_root, run) = authority_support::approved_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Implementation)?;
    gate.bind_thread("thread")?;
    let store = ExtensionData::new("thread");
    let shell = ToolName::plain("exec_command");
    let permit = gate.admit(input(&store, &shell, "thread")).await?;
    authority.fail("backend shutdown failed")?;
    assert!(gate.cancellation().is_cancelled());
    assert_eq!(authority.snapshot()?.state, WorkflowState::Failed);
    assert!(gate.admit(input(&store, &shell, "thread")).await.is_err());
    assert!(authority.update(|_| Ok(())).is_err());
    assert!(authority.start_phase(Phase::Implementation).is_err());
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    drop(permit);
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    let events = fs::read_to_string(authority.artifacts()?.join("runtime-events.jsonl"))?
        .lines()
        .map(serde_json::from_str)
        .collect::<Result<Vec<Value>, _>>()?;
    let failure = events
        .iter()
        .find(|event| event["type"] == "runtime_failed")
        .context("runtime failure event")?;
    assert_eq!(failure["phase_retained"], true);
    assert_eq!(failure["active_dispatches"], 1);
    assert_eq!(failure["shutdown_confirmed"], false);
    assert!(!events.iter().any(|event| event["type"] == "phase_stopped"));
    Ok(())
}
