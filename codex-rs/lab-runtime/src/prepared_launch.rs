//! Fresh launches from frozen data; upstream sessions are never reopened.

use std::path::Path;
use std::time::Instant;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Arg0DispatchPaths;

use crate::HumanReviewer;
use crate::RunOptions;
use crate::RunResult;
use crate::driver_preparation::finish_run;
use crate::driver_preparation::initialize;
use crate::git_evidence::verify_git_baseline;
use crate::prepared;
use crate::prepared::PreparedRunResult;
use crate::prepared_lock;

/// Run immediately, retaining the existing trusted host review boundary.
/// Await through shutdown; dropping the future is not supported recovery.
pub async fn execute_run(options: RunOptions, paths: Arg0DispatchPaths, reviewer: &mut impl HumanReviewer) -> Result<RunResult> {
    let started = Instant::now();
    let _lock = prepared_lock::acquire(&options.repository).await?;
    let driver = initialize(&options, paths, None).await?;
    finish_run(driver, &options, reviewer, started).await
}

/// Finish research/planning and exit with a sealed unapproved checkpoint.
pub async fn prepare_run(options: RunOptions, paths: Arg0DispatchPaths) -> Result<PreparedRunResult> {
    let started = Instant::now();
    let _lock = prepared_lock::acquire(&options.repository).await?;
    let mut driver = initialize(&options, paths, None).await?;
    let result = async {
        driver.prepare_plan(&options).await?;
        let plan = driver.authority.plan()?.context("prepared plan missing")?;
        driver.review_prompts(&options, &plan)?;
        verify_git_baseline(&options.repository, &options.repository_commit).await?;
        driver.evidence.write_json("preparation-metrics.json", &serde_json::json!({
            "schema_version":1,"scope":"preparation only","phase_threads":driver.phase_count,
            "wall_clock_ms":started.elapsed().as_millis(),"task_success":null,
            "input_tokens":driver.outputs.iter().map(|(_,o)|o.token_usage.as_ref().map(|u|u.total_token_usage.input_tokens)).sum::<Option<i64>>(),
            "output_tokens":driver.outputs.iter().map(|(_,o)|o.token_usage.as_ref().map(|u|u.total_token_usage.output_tokens)).sum::<Option<i64>>()
        }))?;
        prepared::seal(&options, &driver.authority, &driver.evidence, driver.phase_count)
    }.await;
    if let Err(error) = &result {
        let _ = driver.authority.fail(&error.to_string());
        let _ = driver.evidence.write_json("failure.json", &serde_json::json!({"error":error.to_string()}));
    }
    result
}

/// Revalidate frozen inputs and ask for a new target-specific human decision.
/// The source run remains immutable and no saved approval is accepted.
pub async fn run_prepared(path: &Path, run_id: String, paths: Arg0DispatchPaths, reviewer: &mut impl HumanReviewer) -> Result<RunResult> {
    let started = Instant::now();
    let before_lock = prepared::load(path, run_id.clone())?;
    let _lock = prepared_lock::acquire(&before_lock.options.repository).await?;
    let checkpoint = prepared::load(path, run_id)?;
    ensure!(checkpoint.lineage == before_lock.lineage, "checkpoint changed while acquiring launch lock");
    let driver = initialize(&checkpoint.options, paths, Some((&checkpoint.settings, &checkpoint.run_spec_sha256))).await?;
    driver.evidence.write_json("parent-preparation.json", &checkpoint.lineage)?;
    finish_run(driver, &checkpoint.options, reviewer, started).await
}
