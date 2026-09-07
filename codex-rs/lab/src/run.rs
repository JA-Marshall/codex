use std::fs;
#[cfg(unix)]
use std::fs::File;
use std::fs::OpenOptions;
use std::io::Write;
use std::panic::AssertUnwindSafe;
use std::path::Path;
use std::path::PathBuf;
use std::time::Instant;
use std::time::SystemTime;
use std::time::UNIX_EPOCH;

use serde::Serialize;

use crate::ActionKind;
use crate::ApprovalTarget;
use crate::JsonRenderer;
use crate::LabError;
use crate::MarkdownRenderer;
use crate::PlanRenderer;
use crate::PlanRevision;
use crate::Renderer;
use crate::ResolvedWorkflow;
use crate::Result;
use crate::RoleInstructions;
use crate::StepProgress;
use crate::VerificationEvidence;
use crate::WorkflowCatalog;
use crate::WorkflowSnapshot;
use crate::digest_bytes;
use crate::workflow::Change;
use crate::workflow::Command;
use crate::workflow::Workflow;
use crate::workflow::bounded_text;

/// Explicit repository evidence supplied by the host; no Git process is launched.
#[derive(Clone, Debug, Serialize)]
pub struct RepositoryMetadata {
    pub commit: String,
    pub initial_dirty_patch_sha256: Option<String>,
}

/// Non-secret provider identity. Unknown observed versions remain absent.
#[derive(Clone, Debug, Serialize)]
pub struct ModelMetadata {
    pub provider: String,
    pub requested_id: String,
    pub observed_version: Option<String>,
    pub catalog_sha256: Option<String>,
    /// Digest of the host's frozen effective runtime settings, excluding secrets.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub effective_config_sha256: Option<String>,
}

/// Frozen effective experimental inputs. It cannot be deserialized into authority.
#[derive(Clone, Debug, Serialize)]
pub struct RunSpec {
    schema_version: u32,
    task: String,
    repository: RepositoryMetadata,
    model: Option<ModelMetadata>,
    workflow_name: String,
    inheritance_chain: Vec<String>,
    workflow: ResolvedWorkflow,
    instructions: RoleInstructions,
    #[serde(skip)]
    source: String,
}

impl RunSpec {
    pub fn resolve(
        catalog: &WorkflowCatalog,
        base: &Path,
        workflow_name: &str,
        task: &str,
        repository: RepositoryMetadata,
        model: Option<ModelMetadata>,
    ) -> Result<Self> {
        bounded_text(task)?;
        if !matches!(repository.commit.len(), 40 | 64)
            || !repository.commit.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(LabError::Invalid(
                "repository commit must be a full Git object ID".into(),
            ));
        }
        if let Some(model) = &model {
            bounded_text(&model.provider)?;
            bounded_text(&model.requested_id)?;
            if let Some(version) = &model.observed_version {
                bounded_text(version)?;
            }
        }
        for hash in [
            repository.initial_dirty_patch_sha256.as_ref(),
            model.as_ref().and_then(|m| m.catalog_sha256.as_ref()),
            model
                .as_ref()
                .and_then(|m| m.effective_config_sha256.as_ref()),
        ]
        .into_iter()
        .flatten()
        {
            if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err(LabError::Invalid(
                    "metadata digest must be SHA-256 hexadecimal".into(),
                ));
            }
        }
        let workflow = catalog.resolve(workflow_name)?;
        let instructions = catalog.resolve_instructions(base, &workflow)?;
        instructions.validate(&workflow.roles)?;
        Ok(Self {
            schema_version: 1,
            task: task.into(),
            repository,
            model,
            workflow_name: workflow_name.into(),
            inheritance_chain: catalog.inheritance_chain(workflow_name)?,
            workflow,
            instructions,
            source: catalog.source().into(),
        })
    }

    pub fn workflow(&self) -> &ResolvedWorkflow {
        &self.workflow
    }

    pub fn instructions(&self) -> &RoleInstructions {
        &self.instructions
    }

    pub fn digest(&self) -> Result<String> {
        // Fixed versioned struct field ordering; nested data has no unordered maps.
        Ok(digest_bytes(&serde_json::to_vec(self)?))
    }
}

/// Single-writer domain workflow with synchronized decisions before admission.
///
/// This is not a live Codex driver. `approve` accepts trusted host human input;
/// model-facing adapters must never expose it as a tool. Artifact location alone
/// does not protect records from a full-access process. No reopening/resume API
/// exists, and filesystem crash recovery is deliberately not implemented.
pub struct LabRun {
    root: PathBuf,
    spec: RunSpec,
    workflow: Workflow,
    sequence: u64,
    started: Instant,
}

#[derive(Serialize)]
struct Event<'a> {
    schema_version: u32,
    sequence: u64,
    unix_ms: u128,
    elapsed_ms: u128,
    change: &'a Change,
    state: crate::WorkflowState,
    approved: Option<&'a ApprovalTarget>,
}

impl LabRun {
    /// `parent` must exist; run IDs are portable directory components. Reusing an
    /// ID fails even after a partial initialization. Only lab-owned files are written.
    pub fn create(parent: &Path, run_id: &str, spec: RunSpec) -> Result<Self> {
        if run_id.is_empty()
            || run_id.len() > 64
            || !run_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
        {
            return Err(LabError::Invalid("invalid run ID".into()));
        }
        let root = parent.canonicalize()?.join(run_id);
        create_directory(&root)?;
        for directory in [
            "config",
            "instructions",
            "plans",
            "decisions",
            "verification",
        ] {
            create_directory(&root.join(directory))?;
        }
        let spec_digest = spec.digest()?;
        write_new(
            &root.join("manifest.json"),
            &serde_json::to_vec_pretty(&serde_json::json!({
                "schema_version": 1, "run_id": run_id, "run_spec_sha256": spec_digest,
                "implementation": "codex-lab-domain-v1", "live_codex_enforcement": false,
                "upstream_trace": {"status": "unavailable", "reason": "offline foundation"},
                "resume_supported": false
            }))?,
        )?;
        write_new(
            &root.join("config/run-spec.json"),
            &serde_json::to_vec_pretty(&spec)?,
        )?;
        write_new(
            &root.join("config/workflow.source.toml"),
            spec.source.as_bytes(),
        )?;
        write_new(
            &root.join("config/workflow.effective.json"),
            &serde_json::to_vec_pretty(&spec.workflow)?,
        )?;
        for (role, instruction) in [
            ("planner", &spec.instructions.planner),
            ("executor", &spec.instructions.executor),
            ("verifier", &spec.instructions.verifier),
        ] {
            write_new(
                &root.join(format!("instructions/{role}.SKILL.md")),
                instruction.content().as_bytes(),
            )?;
        }
        write_new(&root.join("events.jsonl"), b"")?;
        write_new(
            &root.join("metrics.json"),
            &serde_json::to_vec_pretty(&serde_json::json!({
                "schema_version": 1, "status": "unavailable", "reason": "no live evaluator or trace attached",
                "task_success": null, "test_success": null, "hidden_test_success": null,
                "input_tokens": null, "output_tokens": null, "turns": null, "tool_calls": null,
                "planner_calls": null, "files_changed": null, "diff_size": null,
                "human_edits": null, "plan_amendments": null, "plan_deviations": null
            }))?,
        )?;
        let workflow = Workflow::new(run_id.into(), spec_digest);
        let mut run = Self {
            root,
            spec,
            workflow,
            sequence: 0,
            started: Instant::now(),
        };
        run.record(&Change::RunStarted, &run.workflow.snapshot.clone())?;
        Ok(run)
    }

    pub fn snapshot(&self) -> &WorkflowSnapshot {
        &self.workflow.snapshot
    }

    pub fn plan(&self) -> Option<&PlanRevision> {
        self.workflow.plan.as_ref()
    }

    pub fn artifacts(&self) -> &Path {
        &self.root
    }

    pub fn begin_planning(&mut self) -> Result<()> {
        self.transition(Command::BeginPlanning)
    }

    pub fn submit_plan(&mut self, plan: PlanRevision) -> Result<()> {
        self.transition(Command::SubmitPlan(plan))
    }

    /// Import an explicit human edit as a new canonical revision, never as approval.
    pub fn edit_plan(&mut self, plan: PlanRevision, editor: &str, reason: &str) -> Result<()> {
        self.transition(Command::EditPlan {
            plan,
            editor: editor.into(),
            reason: reason.into(),
        })
    }

    /// Trusted host human decision, synchronized to disk before authority is published.
    pub fn approve(&mut self, target: ApprovalTarget, reviewer: &str) -> Result<()> {
        self.transition(Command::Approve {
            target,
            reviewer: reviewer.into(),
        })
    }

    pub fn reject(&mut self, target: ApprovalTarget, reviewer: &str, reason: &str) -> Result<()> {
        self.transition(Command::Reject {
            target,
            reviewer: reviewer.into(),
            reason: reason.into(),
        })
    }

    pub fn request_amendment(&mut self, reason: &str) -> Result<()> {
        self.transition(Command::RequestAmendment(reason.into()))
    }

    pub fn record_step(&mut self, id: &str, progress: StepProgress) -> Result<()> {
        self.transition(Command::RecordStep {
            id: id.into(),
            progress,
        })
    }

    pub fn begin_verification(&mut self) -> Result<()> {
        self.transition(Command::BeginVerification)
    }

    pub fn record_verification(&mut self, id: &str, evidence: VerificationEvidence) -> Result<()> {
        self.transition(Command::RecordVerification {
            id: id.into(),
            evidence,
        })
    }

    pub fn complete(&mut self) -> Result<()> {
        self.transition(Command::Complete)
    }

    pub fn fail(&mut self, reason: &str) -> Result<()> {
        self.transition(Command::Fail(reason.into()))
    }

    /// Check current authority at a synchronous action boundary, recording before
    /// invoking the host closure. No reusable permit is issued. This does not cover
    /// detached/background work; a future live adapter needs admission and draining.
    pub fn perform<T>(
        &mut self,
        target: &ApprovalTarget,
        kind: ActionKind,
        action: impl FnOnce() -> Result<T>,
    ) -> Result<T> {
        self.workflow.admit(target, kind)?;
        if let Err(error) = self.record(
            &Change::ActionAdmitted {
                target: target.clone(),
                kind,
            },
            &self.workflow.snapshot.clone(),
        ) {
            self.workflow.fail_closed();
            return Err(error);
        }
        let outcome = std::panic::catch_unwind(AssertUnwindSafe(action));
        let success = matches!(&outcome, Ok(Ok(_)));
        if !success {
            self.workflow.fail_closed();
        }
        let recorded = self.record(
            &Change::ActionFinished { kind, success },
            &self.workflow.snapshot.clone(),
        );
        if recorded.is_err() {
            self.workflow.fail_closed();
        }
        match outcome {
            Ok(result) => {
                recorded?;
                result
            }
            Err(panic) => std::panic::resume_unwind(panic),
        }
    }

    fn transition(&mut self, command: Command) -> Result<()> {
        let mut next = self.workflow.clone();
        let change = next.apply(command)?;
        // Publish state only after all referenced artifacts and the event are synced.
        let recorded = (|| {
            match &change {
                Change::PlanSubmitted { target } | Change::PlanEdited { target, .. } => {
                    let plan = next
                        .plan
                        .as_ref()
                        .ok_or_else(|| LabError::Invalid("plan missing".into()))?;
                    let directory = self.root.join(format!("plans/{}", target.revision));
                    create_directory(&directory)?;
                    write_new(&directory.join("plan.json"), &plan.canonical_json()?)?;
                    let rendered = match self.spec.workflow.plan.renderer {
                        Renderer::Markdown => MarkdownRenderer.render(plan)?,
                        Renderer::Json => JsonRenderer.render(plan)?,
                    };
                    // Keep canonical storage distinct even when JSON is the chosen view.
                    let filename = match self.spec.workflow.plan.renderer {
                        Renderer::Markdown => "PLAN.md",
                        Renderer::Json => "plan.view.json",
                    };
                    write_new(&directory.join(filename), &rendered.content)?;
                }
                Change::RunStarted
                | Change::PlanningStarted
                | Change::HumanApproved { .. }
                | Change::HumanRejected { .. }
                | Change::AmendmentRequested { .. }
                | Change::StepUpdated { .. }
                | Change::VerificationStarted
                | Change::VerificationRecorded { .. }
                | Change::Completed
                | Change::Failed { .. }
                | Change::ActionAdmitted { .. }
                | Change::ActionFinished { .. } => {}
            }
            if matches!(
                change,
                Change::HumanApproved { .. }
                    | Change::HumanRejected { .. }
                    | Change::PlanEdited { .. }
            ) {
                write_new(
                    &self
                        .root
                        .join(format!("decisions/{}.json", self.sequence + 1)),
                    &serde_json::to_vec_pretty(&change)?,
                )?;
            }
            if matches!(change, Change::VerificationRecorded { .. }) {
                write_new(
                    &self
                        .root
                        .join(format!("verification/{}.json", self.sequence + 1)),
                    &serde_json::to_vec_pretty(&change)?,
                )?;
            }
            self.record(&change, &next.snapshot)
        })();
        if recorded.is_err() {
            self.workflow.fail_closed();
        } else {
            self.workflow = next;
        }
        recorded
    }

    fn record(&mut self, change: &Change, state: &WorkflowSnapshot) -> Result<()> {
        let sequence = self
            .sequence
            .checked_add(1)
            .ok_or_else(|| LabError::Invalid("event sequence exhausted".into()))?;
        let event = Event {
            schema_version: 1,
            sequence,
            unix_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| LabError::Invalid("clock precedes Unix epoch".into()))?
                .as_millis(),
            elapsed_ms: self.started.elapsed().as_millis(),
            change,
            state: state.state,
            approved: state.approved.as_ref(),
        };
        let mut bytes = serde_json::to_vec(&event)?;
        if bytes.len() > 256 * 1024 {
            return Err(LabError::Invalid("journal event exceeds 256 KiB".into()));
        }
        bytes.push(b'\n');
        let mut file = OpenOptions::new()
            .append(true)
            .open(self.root.join("events.jsonl"))?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        self.sequence = sequence;
        Ok(())
    }
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    // Unix directory synchronization persists the new name. Windows File::sync_all
    // flushes file data; this foundation makes no cross-platform crash-resume claim.
    #[cfg(unix)]
    if let Some(parent) = path.parent() {
        File::open(parent)?.sync_all()?;
    }
    Ok(())
}

fn create_directory(path: &Path) -> Result<()> {
    fs::create_dir(path)?;
    #[cfg(unix)]
    if let Some(parent) = path.parent() {
        File::open(parent)?.sync_all()?;
    }
    Ok(())
}
