//! Bounded projections of existing evidence, with explicit missing-control reasons.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_lab::PlanRevision;
use codex_lab::PlanRenderer;
use codex_lab::JsonRenderer;
use codex_lab::MarkdownRenderer;
use serde_json::Value;
use serde_json::json;

use crate::artifact_input::MAX_ARTIFACT_BYTES;
use crate::artifact_input::digest;
use crate::artifact_input::read_artifact;
use crate::comparison::Observation;

pub(crate) fn read_run(root: &Path) -> Result<Observation> {
    let mut source = Source { root, hashes: BTreeMap::new(), bytes: 0 };
    let manifest = source.json("manifest.json")?;
    let spec = source.json("config/run-spec.json")?;
    let settings_bytes = source.read("evidence/effective-settings.json")?;
    let settings: Value = serde_json::from_slice(&settings_bytes)?;
    let events_bytes = source.read("events.jsonl")?;
    let events = journal(&events_bytes)?;
    let last = events.last().context("empty workflow journal")?;
    let target = events.iter().rev().find_map(|e| e["change"].get("target")).context("missing plan target")?;
    let revision = target["revision"].as_u64().context("invalid plan revision")?;
    let plan_bytes = source.read(&format!("plans/{revision}/plan.json"))?;
    let plan: PlanRevision = serde_json::from_slice(&plan_bytes)?;
    ensure!(plan.canonical_json()? == plan_bytes, "stored plan is not canonical");
    let mut problems = Vec::new();
    if last["state"] != "completed" { problems.push("workflow did not complete".into()); }
    if target["run_id"] != manifest["run_id"] || target["run_spec_sha256"] != manifest["run_spec_sha256"]
        || target["content_sha256"] != plan.digest()? {
        problems.push("plan/manifest identity mismatch".into());
    }
    let approvals = events.iter().filter(|e| e["change"]["type"] == "human_approved").count();
    if approvals != 1 || events.iter().any(|e| matches!(e["change"]["type"].as_str(), Some("plan_edited" | "amendment_requested" | "human_rejected"))) {
        problems.push("run does not have exactly one unchanged first-plan approval".into());
    }
    if spec["schema_version"] != 1 || settings["schema_version"] != 1
        || spec["model"]["catalog_sha256"].is_null()
        || spec["model"]["effective_config_sha256"] != digest(&settings_bytes) {
        problems.push("missing or inconsistent model/settings controls".into());
    }
    let mut roles = spec["instructions"].clone();
    let mut role_paths = BTreeMap::new();
    for role in ["planner", "executor", "verifier"] {
        let bytes = source.read(&format!("instructions/{role}.SKILL.md"))?;
        if roles[role]["sha256"] != digest(&bytes) || roles[role]["content"].as_str().map(str::as_bytes) != Some(bytes.as_slice()) {
            problems.push(format!("{role} instruction snapshot mismatch"));
        }
        if let Some(fields) = roles[role].as_object_mut() { role_paths.insert(role, fields.remove("path")); }
    }
    let parent = source.optional("evidence/parent-preparation.json", &mut problems)?;
    if let Some(path) = parent["prepared"].as_str() {
        match crate::prepared::load(Path::new(path), "comparison-data-only".into()) {
            Ok(prepared) => {
                if prepared.lineage != parent || parent["plan_sha256"] != plan.digest()?
                    || prepared.run_spec_sha256 != manifest["run_spec_sha256"] || prepared.settings != settings {
                    problems.push("preparation lineage mismatch".into());
                }
                let parent_root = Path::new(path).parent().and_then(Path::parent).context("invalid parent")?;
                if read_artifact(parent_root, "config/run-spec.json", MAX_ARTIFACT_BYTES)? != source.read("config/run-spec.json")? {
                    problems.push("execution inputs differ from sealed preparation".into());
                }
            }
            Err(error) => problems.push(format!("preparation cannot be validated: {error}")),
        }
    } else { problems.push("missing sealed preparation lineage".into()); }
    let evaluator = source.optional("evaluation/evaluation.json", &mut problems)?;
    for key in ["evaluator_sha256", "fixture_commit", "task_sha256", "python", "sandbox_sha256", "task_success", "hidden_test_success", "public_test_success"] {
        if evaluator[key].is_null() { problems.push(format!("missing evaluator control/outcome: {key}")); }
    }
    if !evaluator.is_null() && (evaluator["fixture_commit"] != spec["repository"]["commit"]
        || evaluator["task_sha256"] != digest(spec["task"].as_str().unwrap_or_default().as_bytes())
        || evaluator["run"].as_str() != root.to_str()) {
        problems.push("evaluator does not match the task/run".into());
    }
    let metrics = source.optional("evidence/metrics.json", &mut problems)?;
    let git = source.optional("evidence/git.json", &mut problems)?;
    if metrics["human_plan_edits"] != 0 || metrics["plan_amendments"] != 0 || metrics["verification_ready"] != true {
        problems.push("metrics do not describe unchanged verified execution".into());
    }
    if git["base_commit"] != spec["repository"]["commit"] || git["final_commit"] != spec["repository"]["commit"] {
        problems.push("final Git evidence differs from the pinned baseline".into());
    }
    let runtime_events = journal(&source.read("runtime-events.jsonl")?)?;
    let mut workflow = spec["workflow"].clone();
    let renderer = workflow.as_object_mut().context("workflow missing")?.remove("plan").context("renderer missing")?;
    let (view_name, view) = match renderer["renderer"].as_str() {
        Some("markdown") => ("PLAN.md", MarkdownRenderer.render(&plan)?),
        Some("json") => ("plan.view.json", JsonRenderer.render(&plan)?),
        _ => anyhow::bail!("unsupported recorded renderer"),
    };
    if source.read(&format!("plans/{revision}/{view_name}"))? != view.content {
        problems.push("rendered plan differs from canonical content".into());
    }
    let mut spec_other = spec.clone();
    for key in ["task", "repository", "model", "workflow", "instructions", "workflow_name", "inheritance_chain"] {
        spec_other.as_object_mut().context("spec missing")?.remove(key);
    }
    let mut evaluator_controls = evaluator.clone();
    if let Some(fields) = evaluator_controls.as_object_mut() {
        for key in ["run", "candidate_files", "public", "api", "checks", "task_success", "public_test_success", "hidden_test_success"] {
            fields.remove(key);
        }
    }
    let controls = json!({"task":spec["task"],"repository":spec["repository"],"model":spec["model"],
        "workflow":workflow,"roles":roles,"settings":settings,"spec_other":spec_other,
        "plan":{"canonical_sha256":plan.digest()?,"renderer":renderer["renderer"]},
        "evaluator":evaluator_controls});
    Ok(Observation { controls, problems,
        metadata:json!({"run":root,"run_id":manifest["run_id"],"run_spec_sha256":manifest["run_spec_sha256"],
            "workflow_name":spec["workflow_name"],"inheritance_chain":spec["inheritance_chain"],"role_paths":role_paths,
            "preparation":parent,"artifact_sha256":source.hashes}),
        outcomes:json!({"workflow_state":last["state"],"metrics":metrics,"git":git,
            "observed_admitted_tools":runtime_events.iter().filter(|e|e["type"] == "tool_admitted").count(),
            "evaluation":evaluator}) })
}

struct Source<'a> { root: &'a Path, hashes: BTreeMap<String,String>, bytes: usize }

impl Source<'_> {
    fn read(&mut self, name: &str) -> Result<Vec<u8>> {
        let bytes = read_artifact(self.root, name, MAX_ARTIFACT_BYTES)?;
        self.bytes += bytes.len();
        ensure!(self.bytes <= 32 * 1024 * 1024, "comparison source exceeds total byte limit");
        self.hashes.insert(name.into(), digest(&bytes));
        Ok(bytes)
    }
    fn json(&mut self, name: &str) -> Result<Value> { Ok(serde_json::from_slice(&self.read(name)?)?) }
    fn optional(&mut self, name: &str, problems: &mut Vec<String>) -> Result<Value> {
        if !self.root.join(name).try_exists()? { problems.push(format!("missing {name}")); return Ok(Value::Null); }
        self.json(name)
    }
}

fn journal(bytes: &[u8]) -> Result<Vec<Value>> {
    let text = std::str::from_utf8(bytes)?;
    ensure!(text.is_empty() || text.ends_with('\n'), "partial event journal");
    text.lines().enumerate().map(|(index,line)| {
        let event: Value = serde_json::from_str(line)?;
        ensure!(event["sequence"] == index + 1, "event journal sequence gap");
        Ok(event)
    }).collect()
}
