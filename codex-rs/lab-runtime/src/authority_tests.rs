use crate::authority_support;

use std::fs::File;

use anyhow::Result;
use codex_extension_api::ExtensionData;
use codex_extension_api::ToolAdmissionContributor;
use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolCallSource;
use codex_extension_api::ToolName;

use super::Phase;
use super::RunAuthority;

#[tokio::test]
async fn runtime_recording_failure_revokes_and_cannot_be_reopened() -> Result<()> {
    let (_root, run) = authority_support::approved_run()?;
    let authority = RunAuthority::new(run)?;
    let gate = authority.start_phase(Phase::Implementation)?;
    gate.bind_thread("thread")?;
    let path = authority.artifacts()?.join("runtime-events.jsonl");
    authority.lock()?.journal = File::open(path)?;
    let store = ExtensionData::new("thread");
    let tool = ToolName::plain("exec_command");
    let result = gate
        .admit(ToolAdmissionInput {
            session_store: &store,
            thread_store: &store,
            turn_store: &store,
            thread_id: "thread",
            turn_id: "turn",
            call_id: "call",
            tool_name: &tool,
            source: ToolCallSource::Direct,
        })
        .await;
    assert!(result.is_err());
    assert!(gate.cancellation().is_cancelled());
    assert!(authority.lock()?.calls.is_empty());
    assert!(authority.finish_phase_after_shutdown(&gate).is_err());
    assert!(authority.update(|_| Ok(())).is_err());
    assert!(authority.start_phase(Phase::Implementation).is_err());
    Ok(())
}
