//! Offline walkthrough: validate inputs, freeze a run, and stop for human review.
use std::collections::BTreeMap;
use std::path::Path;

use codex_lab::LabRun;
use codex_lab::PlanRevision;
use codex_lab::RepositoryMetadata;
use codex_lab::RunSpec;
use codex_lab::WorkflowCatalog;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = std::env::args().skip(1);
    let mut options = BTreeMap::new();
    while let Some(key) = arguments.next() {
        if key == "--help" {
            println!(
                "Offline only: inspect --catalog FILE --base DIR --workflow NAME --plan FILE --output EXISTING_DIR --run-id ID --repository-commit FULL_SHA"
            );
            return Ok(());
        }
        if ![
            "--catalog",
            "--base",
            "--workflow",
            "--plan",
            "--output",
            "--run-id",
            "--repository-commit",
        ]
        .contains(&key.as_str())
        {
            return Err(format!("unknown option {key}").into());
        }
        let value = arguments.next().ok_or("every option requires a value")?;
        if options.insert(key, value).is_some() {
            return Err("duplicate option".into());
        }
    }
    let required = |key| {
        options
            .get(key)
            .map(String::as_str)
            .ok_or_else(|| format!("missing {key}; see --help"))
    };
    let source = std::fs::read_to_string(required("--catalog")?)?;
    let catalog = WorkflowCatalog::parse(&source)?;
    let plan: PlanRevision = serde_json::from_slice(&std::fs::read(required("--plan")?)?)?;
    plan.validate()?;
    let spec = RunSpec::resolve(
        &catalog,
        Path::new(required("--base")?),
        required("--workflow")?,
        &plan.goal,
        RepositoryMetadata {
            commit: required("--repository-commit")?.into(),
            initial_dirty_patch_sha256: None,
        },
        /*model*/ None,
    )?;
    let mut run = LabRun::create(
        Path::new(required("--output")?),
        required("--run-id")?,
        spec,
    )?;
    run.begin_planning()?;
    run.submit_plan(plan)?;
    println!("{}", serde_json::to_string_pretty(run.snapshot())?);
    println!("Artifacts: {}", run.artifacts().display());
    println!(
        "Offline foundation: no model or task tools were started. Explicit human approval is still required."
    );
    Ok(())
}
