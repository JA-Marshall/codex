use std::fs;
use std::path::Path;

use codex_lab::LabRun;
use codex_lab::Renderer;
use codex_lab::RepositoryMetadata;
use codex_lab::Result;
use codex_lab::RunSpec;
use codex_lab::WorkflowCatalog;
use sha2::Digest;
use sha2::Sha256;
use tempfile::TempDir;
use tempfile::tempdir;

pub fn run_spec(base: &Path) -> Result<RunSpec> {
    run_spec_with_renderer(base, Renderer::Markdown)
}

pub fn run_spec_with_renderer(base: &Path, renderer: Renderer) -> Result<RunSpec> {
    run_spec_with_repairs(base, renderer, 0)
}

pub fn run_spec_with_repairs(base: &Path, renderer: Renderer, max_repairs: u8) -> Result<RunSpec> {
    let content = b"---\nname: lab-test-role\ndescription: Exercise the offline lab API.\n---\nFollow the approved canonical plan.\n";
    fs::create_dir_all(base.join("skill"))?;
    fs::write(base.join("skill/SKILL.md"), content)?;
    let sha256 = format!("{:x}", Sha256::digest(content));
    let renderer = match renderer {
        Renderer::Markdown => "markdown",
        Renderer::Json => "json",
    };
    let catalog = WorkflowCatalog::parse(&format!(
        r#"schema_version = 1
[skills.test]
path = "skill"
sha256 = "{sha256}"
[workflows.test]
max_repairs = {max_repairs}
approval = "human_required"
plan.renderer = "{renderer}"
roles.planner = "test"
roles.executor = "test"
roles.verifier = "test"
"#
    ))?;
    RunSpec::resolve(
        &catalog,
        base,
        "test",
        "Exercise the offline workflow",
        RepositoryMetadata {
            commit: "0".repeat(40),
            initial_dirty_patch_sha256: None,
        },
        /*model*/ None,
    )
}

pub fn new_run() -> Result<(TempDir, LabRun)> {
    let root = tempdir()?;
    let spec = run_spec(root.path())?;
    let run = LabRun::create(root.path(), "run", spec)?;
    Ok((root, run))
}
