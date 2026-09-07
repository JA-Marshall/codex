use std::fs;

use anyhow::Context;
use anyhow::Result;
use codex_lab::LabRun;
use codex_lab::PlanRevision;
use codex_lab::RepositoryMetadata;
use codex_lab::RunSpec;
use codex_lab::WorkflowCatalog;
use sha2::Digest;
use sha2::Sha256;
use tempfile::TempDir;

pub fn new_run() -> Result<(TempDir, LabRun)> {
    let root = tempfile::tempdir()?;
    let skill =
        b"---\nname: test\ndescription: Test the runtime gate.\n---\nFollow the approved plan.\n";
    fs::create_dir(root.path().join("skill"))?;
    fs::write(root.path().join("skill/SKILL.md"), skill)?;
    let digest = format!("{:x}", Sha256::digest(skill));
    let catalog = WorkflowCatalog::parse(&format!(
        r#"
schema_version = 1
[skills.test]
path = "skill"
sha256 = "{digest}"
[workflows.test]
approval = "human_required"
plan.renderer = "json"
roles.planner = "test"
roles.executor = "test"
roles.verifier = "test"
"#
    ))?;
    let spec = RunSpec::resolve(
        &catalog,
        root.path(),
        "test",
        "Test runtime admission",
        RepositoryMetadata {
            commit: "0".repeat(40),
            initial_dirty_patch_sha256: None,
        },
        /*model*/ None,
    )?;
    let run = LabRun::create(root.path(), "run", spec)?;
    Ok((root, run))
}

pub fn plan(revision: u32) -> Result<PlanRevision> {
    Ok(serde_json::from_value(serde_json::json!({
        "schema_version":1, "plan_id":"runtime-plan", "revision":revision,
        "goal":"Test runtime admission", "assumptions":[], "risks":[], "discoveries":[], "blockers":[],
        "steps":[{"id":"S01", "title":"Make the change", "instructions":"Implement the approved change",
            "affected_files":["src/example.rs"], "depends_on":[], "acceptance_criteria":["AC01"], "verification":["V01"]}],
        "acceptance_criteria":[{"id":"AC01", "description":"The required change works"}],
        "verification_strategy":[{"id":"V01", "description":"Run the integration tests"}]
    }))?)
}

pub fn approved_run() -> Result<(TempDir, LabRun)> {
    let (root, mut run) = new_run()?;
    run.begin_planning()?;
    run.submit_plan(plan(1)?)?;
    let target = run
        .snapshot()
        .target
        .clone()
        .context("submitted plan target")?;
    run.approve(target, "human")?;
    Ok((root, run))
}
