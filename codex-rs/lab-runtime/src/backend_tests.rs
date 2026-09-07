use crate::authority_support;

use anyhow::Result;
use codex_core_api::Config;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_protocol::protocol::ErrorEvent;
use codex_protocol::protocol::Event;
use codex_protocol::protocol::EventMsg;

use crate::Phase;
use crate::PhaseAccess;
use crate::RunAuthority;

use super::shutdown_and_drain_events;
use super::validate_output_schema;
use super::validate_phase_authority;

#[test]
fn phase_start_requires_its_exact_gate_and_matching_sandbox_access() -> Result<()> {
    let (_research_root, research_run) = authority_support::new_run()?;
    let (_execution_root, execution_run) = authority_support::approved_run()?;
    let research = RunAuthority::new(research_run)?;
    let execution = RunAuthority::new(execution_run)?;
    let research_gate = research.start_phase(Phase::Research)?;
    let execution_gate = execution.start_phase(Phase::Implementation)?;

    let mut incorrect = ExtensionRegistryBuilder::<Config>::new();
    incorrect.tool_admission_contributor(execution_gate.clone());
    assert!(
        validate_phase_authority(&incorrect.build(), &research_gate, PhaseAccess::ReadOnly)
            .is_err()
    );

    let mut correct = ExtensionRegistryBuilder::<Config>::new();
    correct.tool_admission_contributor(research_gate.clone());
    let correct = correct.build();
    validate_phase_authority(&correct, &research_gate, PhaseAccess::ReadOnly)?;
    assert!(
        validate_phase_authority(&correct, &research_gate, PhaseAccess::WorkspaceWrite).is_err()
    );
    research.fail("host cancelled the research phase")?;
    assert!(validate_phase_authority(&correct, &research_gate, PhaseAccess::ReadOnly).is_err());

    let mut executor = ExtensionRegistryBuilder::<Config>::new();
    executor.tool_admission_contributor(execution_gate.clone());
    let executor = executor.build();
    validate_phase_authority(&executor, &execution_gate, PhaseAccess::WorkspaceWrite)?;
    assert!(validate_phase_authority(&executor, &execution_gate, PhaseAccess::ReadOnly).is_err());
    Ok(())
}

#[test]
fn output_schema_budget_includes_serialization_overhead_and_escaping() -> Result<()> {
    validate_output_schema(&serde_json::json!({"type":"object"}))?;
    let oversized = serde_json::json!({"type":"string", "description":"x".repeat(8192)});
    assert!(validate_output_schema(&oversized).is_err());
    let escaped = serde_json::json!({"type":"string", "description":"\n".repeat(4096)});
    assert!(validate_output_schema(&escaped).is_err());
    Ok(())
}

#[tokio::test]
async fn successful_waiter_drains_buffered_graceful_shutdown_evidence() -> Result<()> {
    let marker = Event {
        id: "shutdown".to_string(),
        msg: EventMsg::ShutdownComplete,
    };
    let mut events = Vec::new();
    shutdown_and_drain_events(
        std::future::ready(Ok(())),
        event_stream(vec![marker.clone()]),
        &mut events,
    )
    .await?;
    pretty_assertions::assert_eq!(
        serde_json::to_value(events)?,
        serde_json::to_value(vec![marker])?
    );
    Ok(())
}

#[tokio::test]
async fn graceful_marker_cannot_hide_shutdown_errors() -> Result<()> {
    let queued = vec![
        Event {
            id: "shutdown".to_string(),
            msg: EventMsg::Error(ErrorEvent {
                misalignment: None,
                message: "persistence failed".to_string(),
                codex_error_info: None,
            }),
        },
        Event {
            id: "shutdown".to_string(),
            msg: EventMsg::ShutdownComplete,
        },
    ];
    let mut events = Vec::new();
    let result = shutdown_and_drain_events(
        std::future::ready(Ok(())),
        event_stream(queued),
        &mut events,
    )
    .await;
    assert!(
        result
            .unwrap_err()
            .to_string()
            .contains("persistence failed")
    );
    assert_eq!(events.len(), 2);
    Ok(())
}

#[tokio::test]
async fn terminated_loop_without_marker_fails_for_closed_or_retained_senders() -> Result<()> {
    let mut events = Vec::new();
    let closed = shutdown_and_drain_events(
        std::future::ready(Ok(())),
        || std::future::ready(Err(anyhow::anyhow!("stream closed"))),
        &mut events,
    )
    .await;
    assert!(
        closed
            .unwrap_err()
            .to_string()
            .contains("without a graceful shutdown marker")
    );
    let retained = tokio::time::timeout(
        std::time::Duration::from_secs(1),
        shutdown_and_drain_events(
            std::future::ready(Ok(())),
            std::future::pending,
            &mut events,
        ),
    )
    .await?;
    assert!(
        retained
            .unwrap_err()
            .to_string()
            .contains("without a graceful shutdown marker")
    );
    Ok(())
}

#[tokio::test]
async fn graceful_marker_does_not_replace_a_successful_shutdown_waiter() {
    let mut events = Vec::new();
    let result = shutdown_and_drain_events(
        std::future::ready(Err(anyhow::anyhow!("waiter failed"))),
        event_stream(vec![Event {
            id: "shutdown".to_string(),
            msg: EventMsg::ShutdownComplete,
        }]),
        &mut events,
    )
    .await;
    assert!(result.unwrap_err().to_string().contains("waiter failed"));
}

fn event_stream(
    events: Vec<Event>,
) -> impl FnMut() -> futures::future::BoxFuture<'static, Result<Event>> {
    let queued = std::sync::Arc::new(std::sync::Mutex::new(events.into_iter()));
    move || {
        let queued = std::sync::Arc::clone(&queued);
        Box::pin(async move {
            queued
                .lock()
                .map_err(|_| anyhow::anyhow!("event queue poisoned"))?
                .next()
                .ok_or_else(|| anyhow::anyhow!("stream closed"))
        })
    }
}
