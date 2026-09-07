//! Sealed pending-plan data, deliberately independent of approval authority.

use std::collections::BTreeMap;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_lab::JsonRenderer;
use codex_lab::MarkdownRenderer;
use codex_lab::PlanRenderer;
use codex_lab::PlanRevision;
use codex_lab::Renderer;
use codex_lab::WorkflowState;
use serde::Deserialize;
use serde::Serialize;
use serde_json::Value;

use crate::EvidenceStore;
use crate::RunAuthority;
use crate::RunOptions;
use crate::artifact_input::MAX_ARTIFACT_BYTES;
use crate::artifact_input::digest;
use crate::artifact_input::read_artifact;

const DESCRIPTOR: &str = "evidence/prepared.json";

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Descriptor {
    schema_version: u32,
    repository: PathBuf,
    codex_home: PathBuf,
    runs_directory: PathBuf,
    instruction_root: PathBuf,
    source_run_id: String,
    plan_id: String,
    revision: u32,
    plan_sha256: String,
    run_spec_sha256: String,
    phase_threads: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    verification_input_sha256: Option<String>,
    files: BTreeMap<String, String>,
}

/// A host result, not task completion and not permission to implement.
#[derive(Debug, Serialize)]
pub struct PreparedRunResult {
    pub prepared: PathBuf,
    pub state: WorkflowState,
    pub phase_threads: usize,
}

pub(crate) struct LoadedPrepared {
    pub options: RunOptions,
    pub settings: Value,
    pub run_spec_sha256: String,
    pub lineage: Value,
}

pub(crate) fn seal(
    options: &RunOptions,
    authority: &RunAuthority,
    evidence: &EvidenceStore,
    phase_threads: usize,
) -> Result<PreparedRunResult> {
    let snapshot = authority.snapshot()?;
    ensure!(
        snapshot.state == WorkflowState::AwaitingPlanApproval && snapshot.approved.is_none(),
        "only an unapproved pending plan can be prepared"
    );
    let target = snapshot.target.context("prepared target missing")?;
    let root = authority.artifacts()?;
    let mut descriptor = Descriptor {
        schema_version: 1,
        repository: options.repository.canonicalize()?,
        codex_home: options.codex_home.canonicalize()?,
        runs_directory: options.runs_directory.canonicalize()?,
        instruction_root: options.instruction_root.canonicalize()?,
        source_run_id: target.run_id,
        plan_id: target.plan_id,
        revision: target.revision,
        plan_sha256: target.content_sha256,
        run_spec_sha256: target.run_spec_sha256,
        phase_threads,
        verification_input_sha256: options
            .verification_input
            .as_ref()
            .map(|input| input.bytes().map(|bytes| digest(&bytes)))
            .transpose()?,
        files: BTreeMap::new(),
    };
    let plan = authority.plan()?.context("prepared plan missing")?;
    let renderer = codex_lab::WorkflowCatalog::parse(&options.workflow_catalog)?
        .resolve(&options.workflow)?
        .plan
        .renderer;
    for name in required_files(&descriptor, renderer)? {
        descriptor.files.insert(
            name.clone(),
            digest(&read_artifact(&root, &name, MAX_ARTIFACT_BYTES)?),
        );
    }
    // Validate the exact bytes before publishing the final descriptor. Its mere
    // existence is never enough: every later reader repeats these checks.
    validate_files(&root, &descriptor, &plan, renderer)?;
    let bytes = serde_json::to_vec_pretty(&descriptor)?;
    ensure!(bytes.len() <= 65536, "prepared descriptor exceeds limit");
    let prepared = evidence.write_bytes("prepared.json", &bytes)?;
    Ok(PreparedRunResult {
        prepared,
        state: snapshot.state,
        phase_threads,
    })
}

pub(crate) fn load(path: &Path, run_id: String) -> Result<LoadedPrepared> {
    ensure!(
        !std::fs::symlink_metadata(path)?.file_type().is_symlink(),
        "checkpoint symlinks are unsupported"
    );
    let path = path.canonicalize()?;
    let root = path
        .parent()
        .and_then(Path::parent)
        .context("checkpoint has no run root")?;
    ensure!(
        path == root.join(DESCRIPTOR),
        "expected evidence/prepared.json"
    );
    let bytes = read_artifact(root, DESCRIPTOR, 65536)?;
    let descriptor: Descriptor = serde_json::from_slice(&bytes)?;
    ensure!(
        descriptor.schema_version == 1,
        "unsupported prepared schema"
    );
    ensure!(
        root == descriptor.runs_directory.join(&descriptor.source_run_id),
        "checkpoint moved from original run"
    );
    let spec: Value =
        serde_json::from_slice(&read_artifact(root, "config/run-spec.json", 262144)?)?;
    let catalog = String::from_utf8(read_artifact(root, "config/workflow.source.toml", 65536)?)?;
    let workflow = spec["workflow_name"]
        .as_str()
        .context("missing workflow")?
        .to_owned();
    let renderer = codex_lab::WorkflowCatalog::parse(&catalog)?
        .resolve(&workflow)?
        .plan
        .renderer;
    let plan: PlanRevision = serde_json::from_slice(&read_artifact(
        root,
        &format!("plans/{}/plan.json", descriptor.revision),
        65536,
    )?)?;
    validate_files(root, &descriptor, &plan, renderer)?;
    let task = spec["task"].as_str().context("missing task")?.to_owned();
    ensure!(task.len() <= 8192, "prepared task exceeds limit");
    let settings = serde_json::from_slice(&read_artifact(
        root,
        "evidence/effective-settings.json",
        MAX_ARTIFACT_BYTES,
    )?)?;
    Ok(LoadedPrepared {
        options: RunOptions {
            repository: descriptor.repository,
            repository_commit: spec["repository"]["commit"]
                .as_str()
                .context("missing commit")?
                .to_owned(),
            codex_home: descriptor.codex_home,
            runs_directory: descriptor.runs_directory,
            run_id,
            task,
            workflow_catalog: catalog,
            instruction_root: descriptor.instruction_root,
            workflow,
            plan: Some(plan),
            verification_input: descriptor
                .verification_input_sha256
                .as_ref()
                .map(|_| {
                    crate::VerificationInput::from_json(&read_artifact(
                        root,
                        "evidence/verification-input.json",
                        8192,
                    )?)
                })
                .transpose()?,
        },
        settings,
        lineage: serde_json::json!({"schema_version":1,"prepared":path,"prepared_sha256":digest(&bytes),
            "source_run_id":descriptor.source_run_id,"source_run_spec_sha256":descriptor.run_spec_sha256,
            "plan_sha256":descriptor.plan_sha256,"preparation_phase_threads":descriptor.phase_threads,
            "approval_reused":false}),
        run_spec_sha256: descriptor.run_spec_sha256,
    })
}

fn required_files(descriptor: &Descriptor, renderer: Renderer) -> Result<Vec<String>> {
    ensure!(
        descriptor.phase_threads <= 2,
        "checkpoint contains unexpected phases"
    );
    let mut names: Vec<String> = [
        "manifest.json",
        "config/run-spec.json",
        "config/workflow.source.toml",
        "config/workflow.effective.json",
        "instructions/planner.SKILL.md",
        "instructions/executor.SKILL.md",
        "instructions/verifier.SKILL.md",
        "events.jsonl",
        "runtime-events.jsonl",
        "evidence/effective-settings.json",
        "evidence/environment.json",
        "evidence/runtime-manifest.json",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    let view = match renderer {
        Renderer::Markdown => "PLAN.md",
        Renderer::Json => "plan.view.json",
    };
    names.push(format!("plans/{}/plan.json", descriptor.revision));
    names.push(format!("plans/{}/{view}", descriptor.revision));
    if descriptor.verification_input_sha256.is_some() {
        ensure!(
            descriptor.phase_threads == 0,
            "verifier-only preparation cannot contain model phases"
        );
        names.push("evidence/verification-input.json".into());
    }
    for index in 1..=descriptor.phase_threads {
        names.push(format!("evidence/input-{index:02}.json"));
        names.push(format!("evidence/phase-{index:02}.json"));
    }
    Ok(names)
}

fn validate_files(
    root: &Path,
    descriptor: &Descriptor,
    plan: &PlanRevision,
    renderer: Renderer,
) -> Result<()> {
    let expected = required_files(descriptor, renderer)?;
    ensure!(
        descriptor.files.len() == expected.len(),
        "unexpected checkpoint file inventory"
    );
    let mut artifacts = BTreeMap::new();
    let mut total = 0;
    for name in expected {
        let expected_hash = descriptor
            .files
            .get(&name)
            .context("missing checkpoint artifact")?;
        let bytes = read_artifact(root, &name, MAX_ARTIFACT_BYTES)?;
        total += bytes.len();
        ensure!(
            total <= 32 * 1024 * 1024,
            "checkpoint exceeds total byte limit"
        );
        ensure!(
            digest(&bytes) == *expected_hash,
            "checkpoint artifact changed: {name}"
        );
        artifacts.insert(name, bytes);
    }
    let canonical = plan.canonical_json()?;
    ensure!(
        plan.plan_id == descriptor.plan_id
            && plan.revision == descriptor.revision
            && digest(&canonical) == descriptor.plan_sha256,
        "checkpoint plan identity changed"
    );
    ensure!(
        artifacts[&format!("plans/{}/plan.json", descriptor.revision)] == canonical,
        "plan is not canonical JSON"
    );
    let rendered = match renderer {
        Renderer::Markdown => MarkdownRenderer.render(plan)?,
        Renderer::Json => JsonRenderer.render(plan)?,
    };
    let view = match renderer {
        Renderer::Markdown => "PLAN.md",
        Renderer::Json => "plan.view.json",
    };
    ensure!(
        artifacts[&format!("plans/{}/{view}", descriptor.revision)] == rendered.content,
        "rendered plan differs from canonical plan"
    );
    let manifest: Value = serde_json::from_slice(&artifacts["manifest.json"])?;
    let spec: Value = serde_json::from_slice(&artifacts["config/run-spec.json"])?;
    ensure!(
        spec["verification_input_sha256"].as_str()
            == descriptor.verification_input_sha256.as_deref(),
        "verification input binding differs"
    );
    if let Some(expected) = &descriptor.verification_input_sha256 {
        let bytes = &artifacts["evidence/verification-input.json"];
        let input = crate::VerificationInput::from_json(bytes)?;
        ensure!(
            input.bytes()? == *bytes && digest(bytes) == *expected,
            "verification input changed"
        );
        input.validate(
            plan,
            spec["repository"]["commit"]
                .as_str()
                .context("missing candidate commit")?,
        )?;
    }
    ensure!(
        manifest["run_id"] == descriptor.source_run_id
            && manifest["run_spec_sha256"] == descriptor.run_spec_sha256,
        "checkpoint manifest identity differs"
    );
    let journal = std::str::from_utf8(&artifacts["events.jsonl"])?;
    ensure!(journal.ends_with('\n'), "partial workflow journal");
    let mut last = Value::Null;
    for (index, line) in journal.lines().enumerate() {
        let event: Value = serde_json::from_str(line)?;
        ensure!(
            event["sequence"] == index + 1
                && event["approved"].is_null()
                && matches!(
                    event["state"].as_str(),
                    Some("researching" | "planning" | "awaiting_plan_approval")
                ),
            "checkpoint contains non-pending workflow history"
        );
        last = event;
    }
    ensure!(
        last["state"] == "awaiting_plan_approval"
            && last["change"]["type"] == "plan_submitted"
            && last["change"]["target"]["content_sha256"] == descriptor.plan_sha256
            && last["change"]["target"]["run_spec_sha256"] == descriptor.run_spec_sha256,
        "checkpoint is not a submitted unapproved plan"
    );
    for index in 1..=descriptor.phase_threads {
        let input: Value =
            serde_json::from_slice(&artifacts[&format!("evidence/input-{index:02}.json")])?;
        let output: Value =
            serde_json::from_slice(&artifacts[&format!("evidence/phase-{index:02}.json")])?;
        ensure!(
            matches!(input["phase"].as_str(), Some("research" | "planning"))
                && output["cancelled"] == false,
            "checkpoint contains an incomplete or writable phase"
        );
    }
    crate::prepared_journal::validate(
        &artifacts["runtime-events.jsonl"],
        descriptor.phase_threads,
    )?;
    Ok(())
}

#[cfg(test)]
#[path = "prepared_tests.rs"]
mod tests;
