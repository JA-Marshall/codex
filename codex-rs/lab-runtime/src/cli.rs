use std::io::Read;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use clap::Parser;
use clap::Subcommand;
use codex_core_api::Arg0DispatchPaths;
use codex_lab::PlanRevision;
use codex_lab_runtime::JsonReviewer;
use codex_lab_runtime::RunOptions;
use codex_lab_runtime::TerminalReviewer;
use codex_lab_runtime::compare_runs;
use codex_lab_runtime::execute_run;
use codex_lab_runtime::prepare_run;
use codex_lab_runtime::run_prepared;

#[derive(Parser)]
#[command(
    name = "codex-lab",
    about = "Prepare, review and execute controlled coding workflows"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Compare recorded controls and outcomes without running a model.
    Compare {
        left: PathBuf,
        right: PathBuf,
        #[arg(long)]
        vary: String,
        #[arg(long)]
        output: PathBuf,
    },
    /// Research, plan and ask for human approval in this process.
    Run(Arguments),
    /// Save an unapproved plan and exit after clean phase shutdown.
    Prepare(Arguments),
    /// Validate a saved plan and request a fresh exact human decision.
    RunPrepared {
        #[arg(long)]
        prepared: PathBuf,
        #[arg(long)]
        run_id: String,
        /// Exchange exact-target review requests and decisions as JSON lines on stdio.
        #[arg(long)]
        review_json: bool,
    },
}

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
    let arguments: Vec<_> = std::env::args_os().collect();
    let command = if arguments.get(1).is_some_and(|argument| {
        let text = argument.to_string_lossy();
        text.starts_with('-') && text != "--help" && text != "-h"
    }) {
        Command::Run(Arguments::parse_from(arguments))
    } else {
        Cli::parse_from(arguments).command
    };
    let result = match command {
        Command::Compare {
            left,
            right,
            vary,
            output,
        } => serde_json::to_value(compare_runs(&left, &right, &vary, &output)?)?,
        Command::Run(args) => serde_json::to_value(
            execute_run(args.into_options()?, arg0_paths, &mut TerminalReviewer).await?,
        )?,
        Command::Prepare(args) => {
            serde_json::to_value(prepare_run(args.into_options()?, arg0_paths).await?)?
        }
        Command::RunPrepared {
            prepared,
            run_id,
            review_json,
        } => {
            let result = if review_json {
                run_prepared(&prepared, run_id, arg0_paths, &mut JsonReviewer::default()).await?
            } else {
                run_prepared(&prepared, run_id, arg0_paths, &mut TerminalReviewer).await?
            };
            serde_json::to_value(result)?
        }
    };
    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

impl Arguments {
    fn into_options(self) -> Result<RunOptions> {
        let plan = self
            .plan_file
            .as_ref()
            .map(|path| -> Result<PlanRevision> {
                let plan: PlanRevision = serde_json::from_str(&read_bounded(path, 65536)?)?;
                plan.validate()?;
                Ok(plan)
            })
            .transpose()?;
        Ok(RunOptions {
            repository: self.repository,
            repository_commit: self.commit,
            codex_home: self.codex_home,
            runs_directory: self.runs_directory,
            run_id: self.run_id,
            task: read_bounded(&self.task_file, 8192)?,
            workflow_catalog: read_bounded(&self.workflow_catalog, 65536)?,
            instruction_root: self.instruction_root,
            workflow: self.workflow,
            plan,
        })
    }
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
