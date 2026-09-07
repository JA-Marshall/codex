use std::future::Future;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use anyhow::Result;
use anyhow::bail;
use anyhow::ensure;
use codex_core_api::CodexAppsToolsCache;
use codex_core_api::CodexThread;
use codex_core_api::Config;
use codex_core_api::Feature;
use codex_core_api::LoadUserInstructionsFuture;
use codex_core_api::LoadedUserInstructions;
use codex_core_api::SessionSource;
use codex_core_api::StartIfIdleSubmission;
use codex_core_api::StartThreadOptions;
use codex_core_api::ThreadManager;
use codex_core_api::TurnInputRequest;
use codex_core_api::TurnStartOptions;
use codex_core_api::UserInput;
use codex_core_api::UserInstructionsProvider;
use codex_extension_api::ExtensionRegistry;
use codex_extension_api::ToolAdmissionContributor;
use codex_protocol::protocol::Event;
use codex_protocol::protocol::EventMsg;
use codex_protocol::protocol::TokenUsageInfo;
use futures::FutureExt;
use serde::Serialize;
use serde_json::Value;
use tokio_util::sync::CancellationToken;

use crate::authority::PhaseGate;
use crate::bootstrap::PreparedRuntime;
use crate::context::MAX_PHASE_FRAGMENT_BYTES;
use crate::context::validate_phase_context;
use crate::preflight::PhaseAccess;
use crate::preflight::validate_runtime_config;

const MAX_PHASE_EVENTS: usize = 10_000;
const MAX_PHASE_EVENT_BYTES: usize = 4 * 1024 * 1024;
const MAX_PHASE_DURATION: Duration = Duration::from_secs(30 * 60);

pub struct PhaseRequest {
    pub access: PhaseAccess,
    pub instructions: String,
    pub prompt: String,
    pub output_schema: Option<Value>,
    pub gate: Arc<PhaseGate>,
}

/// Evidence from one real upstream thread. A successful return guarantees the
/// upstream session shutdown finished, including its terminal lifecycle.
#[derive(Debug, Serialize)]
pub struct PhaseOutput {
    pub thread_id: String,
    pub text: String,
    pub token_usage: Option<TokenUsageInfo>,
    pub events: Vec<Event>,
    pub cancelled: bool,
}

/// Restricted embedding of upstream Core. Only ordinary user turns are exposed;
/// approval, direct MCP, UserShellCommand and subagent operations are absent.
pub struct CodexBackend {
    prepared: Arc<PreparedRuntime>,
    extensions: Arc<ExtensionRegistry<Config>>,
}

impl CodexBackend {
    pub fn new(
        prepared: Arc<PreparedRuntime>,
        extensions: Arc<ExtensionRegistry<Config>>,
    ) -> Result<Self> {
        ensure!(
            !extensions.requires_host_skill_discovery(),
            "register ProceduralInstructionsOnly to disable ambient skill discovery"
        );
        ensure!(
            !extensions.tool_admission_contributors().is_empty(),
            "restricted runtime requires a tool admission policy"
        );
        Ok(Self {
            prepared,
            extensions,
        })
    }

    pub fn prepared(&self) -> &PreparedRuntime {
        &self.prepared
    }

    /// Run and shut down one phase. Callers must await this future to completion;
    /// request cancellation through the gate rather than dropping the future.
    /// Arbitrary future cancellation is not an asynchronous cleanup guarantee.
    pub async fn run_phase(&self, request: PhaseRequest) -> Result<PhaseOutput> {
        validate_phase_authority(&self.extensions, &request.gate, request.access)?;
        validate_phase_context(&request.instructions, &request.prompt)?;
        if let Some(schema) = &request.output_schema {
            validate_output_schema(schema)?;
        }
        let cancellation = request.gate.cancellation();
        ensure!(
            !cancellation.is_cancelled(),
            "phase cancelled before startup"
        );
        let mut config = self.prepared.config.clone();
        config.set_legacy_sandbox_policy(request.access.policy())?;
        if request.access == PhaseAccess::WorkspaceWrite {
            config.features.enable(Feature::ShellTool)?;
        }
        config.developer_instructions = Some(request.instructions);
        validate_runtime_config(&config, &self.prepared.paths, request.access)?;
        let expected_profile = config.permissions.effective_permission_profile();
        let expected_model = config.model.clone().context("missing model")?;
        let expected_provider = config.model_provider_id.clone();
        let thread_store =
            codex_core_api::thread_store_from_config(&config, /*state_db*/ None);
        let manager = ThreadManager::new(
            &config,
            Arc::clone(&self.prepared.auth),
            codex_core_api::build_models_manager(&config, Arc::clone(&self.prepared.auth)),
            CodexAppsToolsCache::default(),
            SessionSource::Cli,
            Arc::clone(&self.prepared.environments),
            Arc::clone(&self.extensions),
            Arc::new(NoAmbientUserInstructions),
            /*analytics_events_client*/ None,
            codex_core_api::passthrough_image_store(),
            thread_store,
            /*agent_graph_store*/ None,
            codex_core_api::resolve_installation_id(&config.codex_home).await?,
            /*attestation_provider*/ None,
            /*external_time_provider*/ None,
        );
        let new_thread = manager
            .start_thread(StartThreadOptions::new(config))
            .await?;
        let thread = new_thread.thread;
        let mut output = PhaseOutput {
            thread_id: new_thread.thread_id.to_string(),
            text: String::new(),
            token_usage: None,
            events: vec![Event {
                id: new_thread.thread_id.to_string(),
                msg: EventMsg::SessionConfigured(new_thread.session_configured.clone()),
            }],
            cancelled: false,
        };
        // Effective startup state must agree before the first model call.
        let execution = async {
            request
                .gate
                .bind_thread(&new_thread.thread_id.to_string())?;
            ensure!(
                new_thread.session_configured.permission_profile == expected_profile,
                "upstream changed the effective phase permissions"
            );
            ensure!(
                new_thread.session_configured.model == expected_model,
                "upstream changed the selected model"
            );
            ensure!(
                new_thread.session_configured.model_provider_id == expected_provider,
                "upstream changed the selected provider"
            );
            let submission = TurnInputRequest::user_input(vec![UserInput::Text {
                text: request.prompt,
                text_elements: Vec::new(),
            }])
            .on_start(TurnStartOptions {
                final_output_json_schema: request.output_schema,
                ..Default::default()
            });
            let StartIfIdleSubmission::Started { .. } =
                thread.start_turn_if_idle(submission).await?
            else {
                bail!("upstream declined the phase turn");
            };
            collect_phase(&thread, &cancellation, &mut output).await
        }
        .await;
        // Never cancel or time out shutdown: interruption alone does not stop
        // background terminals. A failure is propagated rather than publishing
        // an amendment-pause/completion claim.
        let shutdown = shutdown_and_drain(&thread, &mut output.events).await;
        output.token_usage = thread.token_usage_info().await;
        shutdown.context("upstream phase shutdown failed")?;
        execution?;
        Ok(output)
    }
}

fn validate_output_schema(schema: &Value) -> Result<()> {
    ensure!(
        serde_json::to_vec(schema)?.len() <= MAX_PHASE_FRAGMENT_BYTES,
        "output schema exceeds byte limit"
    );
    Ok(())
}

fn validate_phase_authority(
    extensions: &ExtensionRegistry<Config>,
    gate: &Arc<PhaseGate>,
    access: PhaseAccess,
) -> Result<()> {
    let expected: Arc<dyn ToolAdmissionContributor> = gate.clone();
    ensure!(
        extensions
            .tool_admission_contributors()
            .iter()
            .any(|contributor| Arc::ptr_eq(contributor, &expected)),
        "the requested phase gate must be registered as a mandatory admission policy"
    );
    ensure!(
        access == gate.expected_access()?,
        "phase access differs from its workflow authority"
    );
    Ok(())
}

struct NoAmbientUserInstructions;

impl UserInstructionsProvider for NoAmbientUserInstructions {
    fn load_user_instructions(&self) -> LoadUserInstructionsFuture<'_> {
        Box::pin(async { LoadedUserInstructions::default() })
    }
}

async fn collect_phase(
    thread: &CodexThread,
    cancellation: &CancellationToken,
    output: &mut PhaseOutput,
) -> Result<()> {
    let deadline = tokio::time::sleep(MAX_PHASE_DURATION);
    tokio::pin!(deadline);
    let mut bytes = serde_json::to_vec(&output.events)?.len();
    loop {
        let event = tokio::select! {
            biased;
            () = cancellation.cancelled() => {
                output.cancelled = true;
                return Ok(());
            }
            () = &mut deadline => bail!("phase exceeded the 30-minute runtime limit"),
            event = thread.next_event() => event?,
        };
        bytes = bytes.saturating_add(serde_json::to_vec(&event)?.len());
        ensure!(
            output.events.len() < MAX_PHASE_EVENTS && bytes <= MAX_PHASE_EVENT_BYTES,
            "phase event evidence limit exceeded"
        );
        let completed = match &event.msg {
            EventMsg::TurnComplete(completed) => {
                ensure!(
                    completed.error.is_none(),
                    "upstream phase completed with an error"
                );
                output.text = completed.last_agent_message.clone().unwrap_or_default();
                true
            }
            EventMsg::Error(error) => bail!("upstream phase error: {}", error.message),
            EventMsg::TurnAborted(_) => bail!("upstream phase aborted unexpectedly"),
            EventMsg::ExecApprovalRequest(_)
            | EventMsg::ApplyPatchApprovalRequest(_)
            | EventMsg::RequestPermissions(_)
            | EventMsg::RequestUserInput(_)
            | EventMsg::DynamicToolCallRequest(_)
            | EventMsg::ElicitationRequest(_) => {
                bail!("unsupported interactive capability requested")
            }
            EventMsg::HookStarted(_)
            | EventMsg::McpToolCallBegin(_)
            | EventMsg::WebSearchBegin(_)
            | EventMsg::ImageGenerationBegin(_) => {
                bail!("unsupported runtime capability became active")
            }
            _ => false,
        };
        output.events.push(event);
        if completed {
            return Ok(());
        }
    }
}

async fn shutdown_and_drain(thread: &CodexThread, events: &mut Vec<Event>) -> Result<()> {
    shutdown_and_drain_events(
        async { Ok(thread.shutdown_and_wait().await?) },
        || async { Ok(thread.next_event().await?) },
        events,
    )
    .await
}

async fn shutdown_and_drain_events<S, N, E>(
    shutdown: S,
    mut next_event: N,
    events: &mut Vec<Event>,
) -> Result<()>
where
    S: Future<Output = Result<()>>,
    N: FnMut() -> E,
    E: Future<Output = Result<Event>>,
{
    tokio::pin!(shutdown);
    let (bytes, error) = match serde_json::to_vec(events) {
        Ok(bytes) => (bytes.len(), None),
        Err(error) => (
            MAX_PHASE_EVENT_BYTES,
            Some(format!("cannot serialize phase evidence: {error}")),
        ),
    };
    let mut evidence = ShutdownEvidence {
        bytes,
        error,
        completed: false,
    };
    let mut stream_open = true;
    loop {
        tokio::select! {
            result = &mut shutdown => {
                result?;
                // The waiter only establishes session-loop termination: it can
                // also succeed after an internal loop failure. Its final marker
                // must already be buffered, so drain ready events without waiting
                // on a sender retained by the terminated session object.
                let mut drained = 0;
                while stream_open && drained < MAX_PHASE_EVENTS {
                    match next_event().now_or_never() {
                        Some(Ok(event)) => {
                            drained += 1;
                            evidence.record(event, events);
                        }
                        Some(Err(_)) | None => stream_open = false,
                    }
                }
                ensure!(drained < MAX_PHASE_EVENTS, "phase shutdown drain limit exceeded");
                if let Some(error) = evidence.error {
                    bail!("{error}");
                }
                ensure!(evidence.completed, "upstream terminated without a graceful shutdown marker");
                return Ok(());
            }
            event = next_event(), if stream_open => match event {
                Ok(event) => evidence.record(event, events),
                Err(_) => stream_open = false,
            },
        }
    }
}

struct ShutdownEvidence {
    bytes: usize,
    error: Option<String>,
    completed: bool,
}

impl ShutdownEvidence {
    fn record(&mut self, event: Event, events: &mut Vec<Event>) {
        match &event.msg {
            EventMsg::ShutdownComplete => self.completed = true,
            EventMsg::Error(error) => {
                self.error = Some(format!("upstream shutdown error: {}", error.message));
            }
            _ => {}
        }
        let event_size = match serde_json::to_vec(&event) {
            Ok(bytes) => bytes.len(),
            Err(error) => {
                self.error = Some(format!("cannot serialize shutdown evidence: {error}"));
                MAX_PHASE_EVENT_BYTES
            }
        };
        self.bytes = self.bytes.saturating_add(event_size);
        if events.len() < MAX_PHASE_EVENTS && self.bytes <= MAX_PHASE_EVENT_BYTES {
            events.push(event);
        } else {
            self.error = Some("phase shutdown evidence limit exceeded".to_string());
        }
    }
}

#[cfg(test)]
#[path = "backend_tests.rs"]
mod tests;
