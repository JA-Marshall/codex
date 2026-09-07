use std::sync::Arc;
use std::time::Instant;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Arg0DispatchPaths;
use codex_lab::LabRun;
use codex_lab::ModelMetadata;
use codex_lab::Renderer;
use codex_lab::RepositoryMetadata;
use codex_lab::RoleInstructions;
use codex_lab::RunSpec;
use codex_lab::WorkflowCatalog;

use crate::EvidenceStore;
use crate::HumanReviewer;
use crate::Phase;
use crate::PhaseOutput;
use crate::PreparedRuntime;
use crate::RunAuthority;
use crate::RunOptions;
use crate::RunResult;
use crate::artifact_input::digest;
use crate::git_evidence::capture_git_diff;
use crate::git_evidence::verify_git_baseline;
use crate::settings::effective_settings;

pub(crate) async fn initialize(
    options: &RunOptions,
    arg0_paths: Arg0DispatchPaths,
    expected: Option<(&serde_json::Value, &str)>,
) -> Result<Driver> {
    let catalog = WorkflowCatalog::parse(&options.workflow_catalog)?;
    let workflow = catalog.resolve(&options.workflow)?;
    verify_git_baseline(&options.repository, &options.repository_commit).await?;
    let runtime = Arc::new(
        PreparedRuntime::load(
            &options.codex_home,
            &options.repository,
            &options.runs_directory,
            Vec::new(),
            arg0_paths,
        )
        .await?,
    );
    let settings = effective_settings(runtime.config())?;
    let settings_bytes = serde_json::to_vec(&settings)?;
    let model = ModelMetadata {
        provider: runtime.config().model_provider_id.clone(),
        requested_id: runtime
            .config()
            .model
            .clone()
            .context("model is not pinned")?,
        observed_version: None,
        catalog_sha256: Some(digest(&serde_json::to_vec(
            &runtime.config().model_catalog,
        )?)),
        effective_config_sha256: Some(digest(&settings_bytes)),
    };
    let mut spec = RunSpec::resolve(
        &catalog,
        &options.instruction_root,
        &options.workflow,
        &options.task,
        RepositoryMetadata {
            commit: options.repository_commit.clone(),
            initial_dirty_patch_sha256: None,
        },
        Some(model),
    )?;
    if let Some(input) = &options.verification_input {
        input.validate(
            options
                .plan
                .as_ref()
                .context("verifier-only trials require an imported plan")?,
            &options.repository_commit,
        )?;
        spec = spec.with_verification_input(&input.bytes()?);
    }
    if let Some((expected_settings, expected_spec)) = expected {
        ensure!(
            &settings == expected_settings,
            "effective runtime settings changed; prepare again"
        );
        ensure!(
            spec.digest()? == expected_spec,
            "effective run specification changed; prepare again"
        );
    }
    let roles = spec.instructions().clone();
    let run = LabRun::create(&options.runs_directory, &options.run_id, spec)?;
    let authority = RunAuthority::new(run)?;
    let evidence = EvidenceStore::new(authority.artifacts()?)?;
    if let Some(input) = &options.verification_input {
        evidence.write_bytes("verification-input.json", &input.bytes()?)?;
    }
    evidence.write_bytes("effective-settings.json", &settings_bytes)?;
    evidence.write_json("environment.json", &serde_json::json!({
        "os":std::env::consts::OS,"arch":std::env::consts::ARCH,
        "lab_version":env!("CARGO_PKG_VERSION"),"repository_commit":options.repository_commit,
        "native_skills":"disabled; frozen procedural modules use developer instructions",
        "trace_root":std::env::var_os("CODEX_ROLLOUT_TRACE_ROOT").map(|p|p.to_string_lossy().into_owned()),
        "trace_completeness":"best effort; local compaction inference may be absent",
        "phase_threads":"fresh per phase","tool_path":"/usr/local/bin:/usr/bin:/bin"
    }))?;
    let driver = Driver {
        authority,
        runtime,
        evidence,
        renderer: workflow.plan.renderer,
        roles,
        phase_count: 0,
        outputs: Vec::new(),
        human_edits: 0,
        amendments: 0,
        first_approval: None,
        amendment_feedback: None,
    };
    driver.evidence.write_json("runtime-manifest.json", &serde_json::json!({
        "schema_version":1,"implementation":"codex-lab-runtime-v1",
        "live_codex_enforcement":true,"domain_manifest":"../manifest.json",
        "domain_manifest_scope":"independent domain library; runtime capabilities are described here",
        "approval":"trusted human input bound to run, plan revision and effective settings",
        "runtime_events":"../runtime-events.jsonl","workflow_events":"../events.jsonl",
        "completion_authority":"terminal workflow event; metrics are prepared before completion",
        "resume_supported":false
    }))?;
    Ok(driver)
}

pub(crate) async fn finish_run(
    mut driver: Driver,
    options: &RunOptions,
    reviewer: &mut impl HumanReviewer,
    started: Instant,
) -> Result<RunResult> {
    let execution: Result<RunResult> = async {
    driver.run(options, reviewer).await?;
    let diff = capture_git_diff(&options.repository, &options.repository_commit).await?;
    driver.evidence.write_bytes("final.diff", &diff.diff)?;
    driver.evidence.write_json("git.json", &serde_json::json!({"base_commit":diff.base_commit,
        "final_commit":diff.final_commit,"files_changed":diff.files_changed,
        "untracked_files":diff.untracked_files,"ignored_untracked_files":"excluded"}))?;
    let input_tokens: Option<i64> = driver.outputs.iter().map(|o| o.1.token_usage.as_ref().map(|u|u.total_token_usage.input_tokens)).sum();
    let output_tokens: Option<i64> = driver.outputs.iter().map(|o| o.1.token_usage.as_ref().map(|u|u.total_token_usage.output_tokens)).sum();
    driver.evidence.write_json("metrics.json", &serde_json::json!({
        "verification_ready":true,"completion_status_source":"events.jsonl terminal workflow event",
        "task_success":null,"hidden_test_success":null,
        "verification_command_results":"passed; semantic adequacy remains reviewer/evaluator responsibility",
        "first_plan_human_approval":driver.first_approval,"human_plan_edits":driver.human_edits,
        "plan_amendments":driver.amendments,"plan_deviations":null,
        "input_tokens":input_tokens,"output_tokens":output_tokens,"turns":driver.phase_count,
        "planner_calls":null,
        "planner_phases":driver.outputs.iter().filter(|o|o.0 == Phase::Planning).count(),
        "wall_clock_ms":started.elapsed().as_millis(),"files_changed":diff.files_changed,"diff_bytes":diff.diff.len(),
        "tool_calls":null,"model_call_metadata":"upstream rollout trace and phase usage evidence"
    }))?;
    // Only the terminal journal event establishes completion. Prepared metrics
    // cannot claim success if this final durable transition fails.
    driver.authority.update(LabRun::complete)?;
    Ok(RunResult {artifacts:driver.authority.artifacts()?,state:driver.authority.snapshot()?.state,phase_threads:driver.phase_count})
    }.await;
    if let Err(error) = &execution {
        let _ = driver.authority.fail(&error.to_string());
        let _ = driver.evidence.write_json("failure.json", &serde_json::json!({"error":error.to_string(),
            "partial_phase_evidence":"consult upstream rollout; collection failure may leave gaps"}));
    }
    execution
}

pub(crate) struct Driver {
    pub authority: RunAuthority,
    pub runtime: Arc<PreparedRuntime>,
    pub evidence: EvidenceStore,
    pub renderer: Renderer,
    pub roles: RoleInstructions,
    pub phase_count: usize,
    pub outputs: Vec<(Phase, PhaseOutput)>,
    pub human_edits: usize,
    pub amendments: usize,
    pub first_approval: Option<bool>,
    pub amendment_feedback: Option<String>,
}
