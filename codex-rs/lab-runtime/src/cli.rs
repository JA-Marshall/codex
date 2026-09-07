use std::io::Read;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use clap::Parser;
use codex_core_api::Arg0DispatchPaths;
use codex_lab::PlanRevision;
use codex_lab_runtime::RunOptions;
use codex_lab_runtime::TerminalReviewer;
use codex_lab_runtime::execute_run;

#[derive(Parser)]
#[command(
    name = "codex-lab",
    about = "Run a restricted Codex workflow with explicit human plan approval"
)]
struct Arguments {
    #[arg(long)]
    repository: PathBuf,
    /// Full pinned Git commit; the repository must initially be clean.
    #[arg(long)]
    commit: String,
    /// Dedicated Codex home containing model/provider configuration.
    #[arg(long)]
    codex_home: PathBuf,
    /// Existing artifact directory outside the task repository.
    #[arg(long)]
    runs_directory: PathBuf,
    #[arg(long)]
    run_id: String,
    #[arg(long)]
    task_file: PathBuf,
    #[arg(long)]
    workflow_catalog: PathBuf,
    #[arg(long)]
    instruction_root: PathBuf,
    #[arg(long)]
    workflow: String,
    /// Reuse canonical JSON; this does not approve the plan.
    #[arg(long)]
    plan_file: Option<PathBuf>,
}

pub async fn run(arg0_paths: Arg0DispatchPaths) -> Result<()> {
    let args = Arguments::parse();
    let plan = args
        .plan_file
        .as_ref()
        .map(|path| -> Result<PlanRevision> {
            let plan: PlanRevision = serde_json::from_str(&read_bounded(path, 65536)?)?;
            plan.validate()?;
            Ok(plan)
        })
        .transpose()?;
    let result = execute_run(
        RunOptions {
            repository: args.repository,
            repository_commit: args.commit,
            codex_home: args.codex_home,
            runs_directory: args.runs_directory,
            run_id: args.run_id,
            task: read_bounded(&args.task_file, 8192)?,
            workflow_catalog: read_bounded(&args.workflow_catalog, 65536)?,
            instruction_root: args.instruction_root,
            workflow: args.workflow,
            plan,
        },
        arg0_paths,
        &mut TerminalReviewer,
    )
    .await?;
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

fn read_bounded(path: &Path, limit: usize) -> Result<String> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)
        .with_context(|| format!("open {}", path.display()))?
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)?;
    ensure!(bytes.len() <= limit, "input file exceeds {limit} bytes");
    Ok(String::from_utf8(bytes)?)
}

#[cfg(test)]
#[path = "cli_tests.rs"]
mod tests;
