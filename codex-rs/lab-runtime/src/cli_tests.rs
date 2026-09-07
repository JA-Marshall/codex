use std::path::PathBuf;

use anyhow::Context;
use clap::Parser;
use clap::error::ErrorKind;
use codex_lab::WorkflowState;
use codex_lab_runtime::RunResult;
use pretty_assertions::assert_eq;

use super::Arguments;
use super::Cli;

#[test]
fn prepared_review_channel_is_explicit_in_cli_help() -> anyhow::Result<()> {
    let help = Cli::try_parse_from(["codex-lab", "run-prepared", "--help"])
        .err().context("expected help")?;
    assert_eq!(help.kind(), ErrorKind::DisplayHelp);
    let rendered = help.to_string().lines().map(str::trim_end).collect::<Vec<_>>().join("\n");
    insta::assert_snapshot!(rendered, @r###"
    Validate a saved plan and request a fresh exact human decision

    Usage: codex-lab run-prepared [OPTIONS] --prepared <PREPARED> --run-id <RUN_ID>

    Options:
          --prepared <PREPARED>
          --run-id <RUN_ID>
          --review-json          Exchange exact-target review requests and decisions as JSON lines on stdio
      -h, --help                 Print help
    "###);
    Ok(())
}

#[test]
fn help_displays_required_inputs_and_explicit_unapproved_plan_option() -> anyhow::Result<()> {
    let help = match Arguments::try_parse_from(["codex-lab", "--help"]) {
        Err(help) => help,
        Ok(_) => anyhow::bail!("help unexpectedly parsed as a runnable task"),
    };
    assert_eq!(help.kind(), ErrorKind::DisplayHelp);
    let rendered = help
        .to_string()
        .lines()
        .map(str::trim_end)
        .collect::<Vec<_>>()
        .join("\n");
    insta::assert_snapshot!(rendered, @r###"
    Run a restricted Codex workflow with explicit human plan approval

    Usage: codex-lab [OPTIONS] --repository <REPOSITORY> --commit <COMMIT> --codex-home <CODEX_HOME> --runs-directory <RUNS_DIRECTORY> --run-id <RUN_ID> --task-file <TASK_FILE> --workflow-catalog <WORKFLOW_CATALOG> --instruction-root <INSTRUCTION_ROOT> --workflow <WORKFLOW>

    Options:
          --repository <REPOSITORY>

          --commit <COMMIT>
              Full pinned Git commit; the repository must initially be clean
          --codex-home <CODEX_HOME>
              Dedicated Codex home containing model/provider configuration
          --runs-directory <RUNS_DIRECTORY>
              Existing artifact directory outside the task repository
          --run-id <RUN_ID>

          --task-file <TASK_FILE>

          --workflow-catalog <WORKFLOW_CATALOG>

          --instruction-root <INSTRUCTION_ROOT>

          --workflow <WORKFLOW>

          --plan-file <PLAN_FILE>
              Reuse canonical JSON; this does not approve the plan
      -h, --help
              Print help
    "###);
    Ok(())
}

#[test]
fn completed_run_result_has_stable_cli_json_shape() -> anyhow::Result<()> {
    let result = RunResult {
        artifacts: PathBuf::from("runs/run-1"),
        state: WorkflowState::Completed,
        phase_threads: 4,
    };
    insta::assert_snapshot!(serde_json::to_string_pretty(&result)?, @r###"
    {
      "artifacts": "runs/run-1",
      "state": "completed",
      "phase_threads": 4
    }
    "###);
    Ok(())
}
