#![allow(clippy::expect_used)]

use std::sync::Arc;
use std::sync::Mutex;

use codex_extension_api::ExtensionData;
use codex_extension_api::ExtensionFuture;
use codex_extension_api::ExtensionRegistryBuilder;
use codex_extension_api::ToolAdmissionContributor;
use codex_extension_api::ToolAdmissionError;
use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolAdmissionPermit;
use codex_extension_api::ToolCallSource;
use codex_extension_api::ToolName;
use pretty_assertions::assert_eq;

#[derive(Clone, Copy)]
enum Decision {
    Admit,
    Deny,
    Wait,
}

struct Policy {
    decision: Decision,
    events: Arc<Mutex<Vec<&'static str>>>,
}

struct Lease(Arc<Mutex<Vec<&'static str>>>);

impl Drop for Lease {
    fn drop(&mut self) {
        self.0.lock().expect("event lock").push("released");
    }
}

impl ToolAdmissionContributor for Policy {
    fn admit<'a>(
        &'a self,
        input: ToolAdmissionInput<'a>,
    ) -> ExtensionFuture<'a, Result<ToolAdmissionPermit, ToolAdmissionError>> {
        Box::pin(async move {
            assert_eq!(input.thread_id, "thread");
            match self.decision {
                Decision::Admit => {
                    self.events.lock().expect("event lock").push("admitted");
                    Ok(ToolAdmissionPermit::new(Lease(Arc::clone(&self.events))))
                }
                Decision::Deny => {
                    self.events.lock().expect("event lock").push("denied");
                    Err(ToolAdmissionError::new("approval required"))
                }
                Decision::Wait => {
                    self.events.lock().expect("event lock").push("waiting");
                    std::future::pending().await
                }
            }
        })
    }
}

fn input<'a>(store: &'a ExtensionData, name: &'a ToolName) -> ToolAdmissionInput<'a> {
    ToolAdmissionInput {
        session_store: store,
        thread_store: store,
        turn_store: store,
        thread_id: "thread",
        turn_id: "turn",
        call_id: "call",
        tool_name: name,
        source: ToolCallSource::Direct,
    }
}

#[tokio::test]
async fn admission_requires_every_policy_and_releases_prior_permits_on_denial() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut builder = ExtensionRegistryBuilder::<()>::new();
    for decision in [Decision::Admit, Decision::Deny, Decision::Admit] {
        builder.tool_admission_contributor(Arc::new(Policy {
            decision,
            events: Arc::clone(&events),
        }));
    }
    let store = ExtensionData::new("thread");
    let name = ToolName::plain("exec_command");
    let error = builder.build().admit_tool(input(&store, &name)).await.err();
    assert_eq!(error, Some(ToolAdmissionError::new("approval required")));
    assert_eq!(
        *events.lock().expect("event lock"),
        ["admitted", "denied", "released"]
    );
}

#[tokio::test]
async fn successful_admission_retains_all_permits_until_the_host_drops_them() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut builder = ExtensionRegistryBuilder::<()>::new();
    for _ in 0..2 {
        builder.tool_admission_contributor(Arc::new(Policy {
            decision: Decision::Admit,
            events: Arc::clone(&events),
        }));
    }
    let store = ExtensionData::new("thread");
    let name = ToolName::plain("exec_command");
    let permits = builder
        .build()
        .admit_tool(input(&store, &name))
        .await
        .expect("admitted");
    assert_eq!(
        *events.lock().expect("event lock"),
        ["admitted", "admitted"]
    );
    drop(permits);
    assert_eq!(
        *events.lock().expect("event lock"),
        ["admitted", "admitted", "released", "released"]
    );
}

#[tokio::test]
async fn cancelling_admission_releases_permits_from_earlier_policies() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut builder = ExtensionRegistryBuilder::<()>::new();
    for decision in [Decision::Admit, Decision::Wait] {
        builder.tool_admission_contributor(Arc::new(Policy {
            decision,
            events: Arc::clone(&events),
        }));
    }
    let registry = builder.build();
    let store = ExtensionData::new("thread");
    let name = ToolName::plain("exec_command");
    let mut admission = Box::pin(registry.admit_tool(input(&store, &name)));
    assert!(
        std::future::poll_fn(|context| {
            std::task::Poll::Ready(admission.as_mut().poll(context))
        })
        .await
        .is_pending()
    );
    drop(admission);
    assert_eq!(
        *events.lock().expect("event lock"),
        ["admitted", "waiting", "released"]
    );
}

#[tokio::test]
async fn empty_registry_preserves_existing_dispatch() {
    let store = ExtensionData::new("thread");
    let name = ToolName::plain("exec_command");
    let permits = ExtensionRegistryBuilder::<()>::new()
        .build()
        .admit_tool(input(&store, &name))
        .await
        .expect("no additional policy");
    assert!(permits.is_empty());
}

#[test]
fn denial_reason_has_a_unicode_safe_bound() {
    let error = ToolAdmissionError::new("🧪".repeat(600));
    assert_eq!(error.to_string(), "🧪".repeat(512));
}
