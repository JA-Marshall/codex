use std::collections::BTreeMap;
use std::fs::File;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::MutexGuard;
use std::sync::Weak;
use std::time::Instant;
use std::time::SystemTime;
use std::time::UNIX_EPOCH;

use anyhow::Context;
use anyhow::Result;
use anyhow::bail;
use codex_extension_api::ExtensionFuture;
use codex_extension_api::ToolAdmissionContributor;
use codex_extension_api::ToolAdmissionError;
use codex_extension_api::ToolAdmissionInput;
use codex_extension_api::ToolAdmissionPermit;
use codex_extension_api::ToolCallOutcome;
use codex_extension_api::ToolFinishInput;
use codex_extension_api::ToolLifecycleContributor;
use codex_extension_api::ToolLifecycleFuture;
use codex_lab::ApprovalTarget;
use codex_lab::LabRun;
use codex_lab::PlanRevision;
use codex_lab::WorkflowSnapshot;
use codex_lab::WorkflowState;
use codex_tools::ToolCallSource;
use serde::Serialize;
use tokio_util::sync::CancellationToken;

use crate::preflight::PhaseAccess;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Phase {
    Research,
    Planning,
    Implementation,
    Verification,
}

impl Phase {
    fn accepts_state(self, state: WorkflowState) -> bool {
        matches!(
            (self, state),
            (Self::Research, WorkflowState::Researching)
                | (
                    Self::Planning,
                    WorkflowState::Planning | WorkflowState::AwaitingPlanAmendment
                )
                | (Self::Implementation, WorkflowState::Implementing)
                | (Self::Verification, WorkflowState::Verifying)
        )
    }

    fn allows(self, name: &str) -> bool {
        match name {
            "lab_repo_read" | "lab_repo_list" => true,
            "lab_request_amendment" | "exec_command" => {
                matches!(self, Self::Implementation | Self::Verification)
            }
            "apply_patch" => self == Self::Implementation,
            _ => false,
        }
    }
}

struct ActivePhase {
    epoch: u64,
    phase: Phase,
    target: Option<ApprovalTarget>,
    cancellation: CancellationToken,
    revoked: bool,
    amendment: Option<String>,
    thread_id: Option<String>,
}

struct State {
    run: LabRun,
    journal: File,
    sequence: u64,
    epoch: u64,
    phase: Option<ActivePhase>,
    calls: BTreeMap<String, bool>,
    faulted: bool,
    started: Instant,
}

/// Trusted, single-writer authority shared by the host and its dispatch contributors.
///
/// Human transitions are accepted only between phase threads. Model tools receive
/// only a phase gate and amendment capability, never a host approval operation.
#[derive(Clone)]
pub struct RunAuthority {
    inner: Arc<Mutex<State>>,
}

impl RunAuthority {
    pub fn new(run: LabRun) -> Result<Self> {
        let journal = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(run.artifacts().join("runtime-events.jsonl"))?;
        journal.sync_all()?;
        #[cfg(unix)]
        File::open(run.artifacts())?.sync_all()?;
        Ok(Self {
            inner: Arc::new(Mutex::new(State {
                run,
                journal,
                sequence: 0,
                epoch: 0,
                phase: None,
                calls: BTreeMap::new(),
                faulted: false,
                started: Instant::now(),
            })),
        })
    }

    fn lock(&self) -> Result<MutexGuard<'_, State>> {
        self.inner
            .lock()
            .map_err(|_| anyhow::anyhow!("run authority poisoned"))
    }

    /// Apply a trusted human or host observation while no phase can admit tools.
    pub fn update<T>(&self, action: impl FnOnce(&mut LabRun) -> codex_lab::Result<T>) -> Result<T> {
        let mut state = self.lock()?;
        if state.faulted || state.phase.is_some() || !state.calls.is_empty() {
            bail!("host transitions require a healthy, stopped phase");
        }
        Ok(action(&mut state.run)?)
    }

    /// Revokes runtime authority immediately and records a terminal host failure.
    ///
    /// This may run during a phase, including after failed upstream shutdown. It
    /// retains phase and dispatch accounting and never claims processes stopped.
    /// Revocation remains effective even if either journal cannot record failure.
    pub fn fail(&self, reason: &str) -> Result<()> {
        let mut state = self.lock()?;
        state.faulted = true;
        if let Some(phase) = &mut state.phase {
            phase.revoked = true;
            phase.cancellation.cancel();
        }
        let reason: String = reason.chars().take(1024).collect();
        let reason = if reason.trim().is_empty() {
            "runtime failed"
        } else {
            &reason
        };
        let failed = if state.run.snapshot().state == WorkflowState::Failed {
            Ok(())
        } else {
            state.run.fail(reason)
        };
        let phase_retained = state.phase.is_some();
        let active_dispatches = state.calls.len();
        let recorded = state.record(serde_json::json!({"type":"runtime_failed", "reason":reason,
            "phase_retained":phase_retained,"active_dispatches":active_dispatches,
            "shutdown_confirmed":false}));
        failed?;
        recorded
    }

    pub fn snapshot(&self) -> Result<WorkflowSnapshot> {
        Ok(self.lock()?.run.snapshot().clone())
    }

    pub fn plan(&self) -> Result<Option<PlanRevision>> {
        Ok(self.lock()?.run.plan().cloned())
    }

    pub fn artifacts(&self) -> Result<PathBuf> {
        Ok(self.lock()?.run.artifacts().to_path_buf())
    }

    pub fn start_phase(&self, phase: Phase) -> Result<Arc<PhaseGate>> {
        let mut state = self.lock()?;
        if state.faulted || state.phase.is_some() || !state.calls.is_empty() {
            bail!("previous phase has not stopped cleanly");
        }
        if !phase.accepts_state(state.run.snapshot().state) {
            bail!("workflow state does not permit {phase:?}");
        }
        let target = match phase {
            Phase::Implementation | Phase::Verification => {
                let snapshot = state.run.snapshot();
                if snapshot.approved.is_none() || snapshot.approved != snapshot.target {
                    bail!("current plan has not been approved");
                }
                snapshot.approved.clone()
            }
            Phase::Research | Phase::Planning => None,
        };
        state.epoch = state
            .epoch
            .checked_add(1)
            .context("phase epoch exhausted")?;
        let epoch = state.epoch;
        let cancellation = CancellationToken::new();
        state.record(serde_json::json!({"type":"phase_started", "epoch":epoch,
            "phase":phase, "target":target}))?;
        state.phase = Some(ActivePhase {
            epoch,
            phase,
            target,
            cancellation: cancellation.clone(),
            revoked: false,
            amendment: None,
            thread_id: None,
        });
        Ok(Arc::new(PhaseGate {
            authority: self.clone(),
            epoch,
            cancellation,
        }))
    }

    /// The host MUST await upstream thread/process shutdown before calling this.
    /// Active dispatch accounting alone does not establish subprocess termination.
    pub fn finish_phase_after_shutdown(&self, gate: &PhaseGate) -> Result<Option<String>> {
        if !Arc::ptr_eq(&self.inner, &gate.authority.inner) {
            bail!("phase belongs to a different run authority");
        }
        let mut state = self.lock()?;
        if state.faulted {
            bail!("run recording failed; authority remains revoked");
        }
        if !state.calls.is_empty() {
            bail!("tool dispatches remain active after thread shutdown");
        }
        let active = state.phase.as_ref().context("no active phase")?;
        if active.epoch != gate.epoch {
            bail!("stale phase shutdown acknowledgement");
        }
        let amendment = active.amendment.clone();
        state.record(serde_json::json!({"type":"phase_stopped", "epoch":gate.epoch}))?;
        state.phase = None;
        if let Some(reason) = &amendment {
            state.run.request_amendment(reason)?;
        }
        Ok(amendment)
    }
}

/// A capability scope for exactly one phase thread. It cannot approve a plan.
pub struct PhaseGate {
    authority: RunAuthority,
    epoch: u64,
    cancellation: CancellationToken,
}

impl PhaseGate {
    pub(crate) fn expected_access(&self) -> Result<PhaseAccess> {
        let state = self.authority.lock()?;
        let active = state.phase.as_ref().context("no active phase")?;
        if state.faulted
            || active.epoch != self.epoch
            || active.revoked
            || self.cancellation.is_cancelled()
        {
            bail!("phase authority is unavailable");
        }
        Ok(match active.phase {
            Phase::Research | Phase::Planning => PhaseAccess::ReadOnly,
            Phase::Implementation | Phase::Verification => PhaseAccess::WorkspaceWrite,
        })
    }

    /// Binds this authority once to the host-created thread, before its first turn.
    /// Unbound gates and other threads cannot obtain tool admission.
    pub fn bind_thread(&self, thread_id: &str) -> Result<()> {
        if thread_id.is_empty() || thread_id.len() > 512 || thread_id.contains('\0') {
            bail!("invalid phase thread identity");
        }
        let mut state = self.authority.lock()?;
        if state.faulted {
            bail!("run authority unavailable");
        }
        let active = state.phase.as_ref().context("no active phase")?;
        if active.epoch != self.epoch
            || active.revoked
            || self.cancellation.is_cancelled()
            || active.thread_id.is_some()
        {
            bail!("phase must be healthy, current, and unbound");
        }
        state.record(
            serde_json::json!({"type":"phase_thread_bound", "epoch":self.epoch,
            "thread_id":thread_id}),
        )?;
        state.phase.as_mut().context("no active phase")?.thread_id = Some(thread_id.to_owned());
        Ok(())
    }

    pub fn cancellation(&self) -> CancellationToken {
        self.cancellation.clone()
    }

    pub fn request_amendment(&self, reason: &str) -> Result<()> {
        if reason.trim().is_empty() || reason.len() > 4096 {
            bail!("amendment reason must contain 1..4096 bytes");
        }
        let mut state = self.authority.lock()?;
        let active = state.phase.as_mut().context("no active phase")?;
        if active.epoch != self.epoch
            || active.revoked
            || !matches!(active.phase, Phase::Implementation | Phase::Verification)
        {
            bail!("amendment requires an active approved execution phase");
        }
        // Revoke before recording. Even recording failure cannot leave authority live.
        active.revoked = true;
        active.amendment = Some(reason.to_owned());
        active.cancellation.cancel();
        state.record(
            serde_json::json!({"type":"admission_revoked", "epoch":self.epoch,
            "reason":reason}),
        )
    }
}

impl ToolAdmissionContributor for PhaseGate {
    fn admit<'a>(
        &'a self,
        input: ToolAdmissionInput<'a>,
    ) -> ExtensionFuture<'a, Result<ToolAdmissionPermit, ToolAdmissionError>> {
        Box::pin(async move {
            let result = (|| -> Result<ToolAdmissionPermit> {
                let mut state = self.authority.lock()?;
                if state.faulted {
                    bail!("run authority unavailable");
                }
                let active = state.phase.as_ref().context("phase is stopped")?;
                if active.epoch != self.epoch || active.revoked || self.cancellation.is_cancelled()
                {
                    bail!("phase authority revoked");
                }
                if active.thread_id.as_deref() != Some(input.thread_id) {
                    bail!("tool thread is not bound to this phase");
                }
                if input.source != ToolCallSource::Direct
                    || !input.tool_name.is_default_namespace()
                    || !active.phase.allows(&input.tool_name.name)
                {
                    bail!("tool capability is unavailable in this workflow phase");
                }
                let snapshot = state.run.snapshot();
                if !active.phase.accepts_state(snapshot.state)
                    || (active.target.is_some()
                        && (snapshot.approved != active.target || snapshot.target != active.target))
                {
                    bail!("current plan approval no longer matches phase authority");
                }
                if [input.thread_id, input.turn_id, input.call_id]
                    .iter()
                    .any(|id| id.is_empty() || id.len() > 512 || id.contains('\0'))
                {
                    bail!("invalid tool identity");
                }
                let key = format!("{}\0{}\0{}", input.thread_id, input.turn_id, input.call_id);
                if state.calls.contains_key(&key) {
                    bail!("duplicate active tool identity");
                }
                let epoch = active.epoch;
                let target = active.target.clone();
                state.record(serde_json::json!({"type":"tool_admitted", "epoch":epoch,
                    "thread_id":input.thread_id,"turn_id":input.turn_id,"call_id":input.call_id,
                    "tool":input.tool_name.to_string(),"approved":target}))?;
                state.calls.insert(key.clone(), false);
                Ok(ToolAdmissionPermit::new(CallLease {
                    state: Arc::downgrade(&self.authority.inner),
                    key,
                }))
            })();
            result.map_err(|error| ToolAdmissionError::new(error.to_string()))
        })
    }
}

impl ToolLifecycleContributor for PhaseGate {
    fn on_tool_finish<'a>(&'a self, input: ToolFinishInput<'a>) -> ToolLifecycleFuture<'a> {
        Box::pin(async move {
            if let Ok(mut state) = self.authority.lock() {
                let Some(active) = state
                    .phase
                    .as_ref()
                    .filter(|active| active.epoch == self.epoch)
                else {
                    return;
                };
                let Some(thread_id) = &active.thread_id else {
                    return;
                };
                if input.thread_store.level_id() != thread_id {
                    return;
                }
                let key = format!("{thread_id}\0{}\0{}", input.turn_id, input.call_id);
                if state.calls.contains_key(&key) {
                    let outcome = match input.outcome {
                        ToolCallOutcome::Completed { success } => {
                            serde_json::json!({"type":"completed", "success":success})
                        }
                        ToolCallOutcome::Blocked => serde_json::json!({"type":"blocked"}),
                        ToolCallOutcome::Failed { handler_executed } => {
                            serde_json::json!({"type":"failed", "handler_executed":handler_executed})
                        }
                        ToolCallOutcome::Aborted => serde_json::json!({"type":"aborted"}),
                    };
                    let result = state.record(serde_json::json!({"type":"tool_finished",
                        "epoch":self.epoch,"turn_id":input.turn_id,"call_id":input.call_id,"outcome":outcome}));
                    if result.is_ok() {
                        state.calls.insert(key, true);
                    }
                }
            }
        })
    }
}

struct CallLease {
    state: Weak<Mutex<State>>,
    key: String,
}

impl Drop for CallLease {
    fn drop(&mut self) {
        if let Some(shared) = self.state.upgrade()
            && let Ok(mut state) = shared.lock()
            && let Some(finished) = state.calls.remove(&self.key)
            && !finished
        {
            let _ =
                state.record(serde_json::json!({"type":"dispatch_dropped", "identity":self.key}));
        }
    }
}

impl State {
    fn record(&mut self, mut event: serde_json::Value) -> Result<()> {
        let result = (|| -> Result<()> {
            self.sequence = self
                .sequence
                .checked_add(1)
                .context("runtime event sequence exhausted")?;
            event["sequence"] = self.sequence.into();
            event["schema_version"] = 1.into();
            event["elapsed_ms"] = u64::try_from(self.started.elapsed().as_millis())
                .context("runtime elapsed time exhausted")?
                .into();
            event["unix_ms"] =
                u64::try_from(SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis())
                    .context("runtime wall time exhausted")?
                    .into();
            let mut bytes = serde_json::to_vec(&event)?;
            if bytes.len() > 16384 {
                bail!("runtime event exceeds bound");
            }
            bytes.push(b'\n');
            self.journal.write_all(&bytes)?;
            self.journal.sync_all()?;
            Ok(())
        })();
        if result.is_err() {
            self.faulted = true;
            if let Some(phase) = &mut self.phase {
                phase.revoked = true;
                phase.cancellation.cancel();
            }
        }
        result
    }
}

#[cfg(test)]
#[path = "authority_tests.rs"]
mod tests;
