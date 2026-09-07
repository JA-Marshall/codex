//! Explicit, bounded delegation for a single trial in an unattended campaign.

use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;
use std::time::Instant;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Arg0DispatchPaths;
use codex_lab::ApprovalPolicy;
use codex_lab::ApprovalTarget;
use codex_lab::RenderedPlan;
use codex_lab::WorkflowCatalog;
use serde::Deserialize;

use crate::HumanDecision;
use crate::HumanReviewer;
use crate::RunOptions;
use crate::RunResult;
use crate::artifact_input::digest;
use crate::driver_preparation::finish_run;
use crate::driver_preparation::initialize;
use crate::prepared_lock;

const MAX_POLICY_BYTES: usize = 16 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CampaignPolicy {
    schema_version: u32,
    campaign_id: String,
    run_id: String,
    repository: PathBuf,
    repository_commit: String,
    task_sha256: String,
    workflow: String,
    workflow_catalog_sha256: String,
    #[serde(default)]
    max_amendments: u8,
}

/// Run one explicitly delegated trial without reading terminal decisions.
/// The policy is immutable for this launch and copied to host-owned evidence
/// before any model phase. It binds task identity, not the semantic adequacy of
/// generated plans; sandbox restrictions and independent evaluation still apply.
pub async fn execute_campaign_run(
    options: RunOptions,
    paths: Arg0DispatchPaths,
    policy_path: &Path,
) -> Result<RunResult> {
    let started = Instant::now();
    let (policy, bytes) = CampaignPolicy::load(policy_path, &options)?;
    let policy_sha256 = digest(&bytes);
    let _lock = prepared_lock::acquire(&options.repository).await?;
    let mut driver = initialize(&options, paths, None).await?;
    driver
        .evidence
        .write_bytes("campaign-policy.json", &bytes)?;
    driver.evidence.write_json(
        "campaign-authorization.json",
        &serde_json::json!({
            "schema_version":1,"campaign_id":policy.campaign_id,
            "policy_sha256":policy_sha256,"approval":"campaign_delegated",
            "scope":"fixed task, repository, commit and workflow; generated plan semantics are not checked",
            "max_amendments":policy.max_amendments
        }),
    )?;
    driver.delegation_sha256 = Some(policy_sha256.clone());
    driver.max_amendments = Some(policy.max_amendments);
    let mut reviewer = CampaignReviewer {
        run_id: policy.run_id,
        policy_sha256,
    };
    finish_run(driver, &options, &mut reviewer, started).await
}

impl CampaignPolicy {
    fn load(path: &Path, options: &RunOptions) -> Result<(Self, Vec<u8>)> {
        ensure!(
            options.repository.is_absolute(),
            "campaign repository must be absolute"
        );
        let repository = options.repository.canonicalize()?;
        let path = path.canonicalize().context("resolve campaign policy")?;
        ensure!(
            !path.starts_with(&repository),
            "campaign policy must be outside the model-writable repository"
        );
        let metadata = std::fs::metadata(&path)?;
        ensure!(
            metadata.is_file() && metadata.len() <= MAX_POLICY_BYTES as u64,
            "campaign policy exceeds regular file limit"
        );
        let file = File::open(path).context("open campaign policy")?;
        let mut bytes = Vec::new();
        file.take(MAX_POLICY_BYTES as u64 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() <= MAX_POLICY_BYTES,
            "campaign policy grew beyond limit"
        );
        let policy: Self = serde_json::from_slice(&bytes).context("parse campaign policy")?;
        ensure!(
            policy.schema_version == 1,
            "unsupported campaign policy schema"
        );
        ensure!(
            !policy.campaign_id.is_empty()
                && policy.campaign_id.len() <= 128
                && policy
                    .campaign_id
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte)),
            "campaign ID must be a bounded portable identifier"
        );
        ensure!(
            policy.run_id == options.run_id,
            "campaign policy run ID mismatch"
        );
        ensure!(
            policy.repository.is_absolute() && policy.repository.canonicalize()? == repository,
            "campaign policy repository mismatch or nonabsolute repository"
        );
        ensure!(
            policy.repository_commit == options.repository_commit,
            "campaign policy repository commit mismatch"
        );
        ensure!(
            policy.task_sha256 == digest(options.task.as_bytes()),
            "campaign policy task digest mismatch"
        );
        ensure!(
            policy.workflow == options.workflow,
            "campaign policy workflow mismatch"
        );
        ensure!(
            policy.workflow_catalog_sha256 == digest(options.workflow_catalog.as_bytes()),
            "campaign policy workflow catalog digest mismatch"
        );
        ensure!(
            policy.max_amendments <= 4,
            "campaign policy amendment limit must be between 0 and 4"
        );
        let catalog = WorkflowCatalog::parse(&options.workflow_catalog)?;
        ensure!(
            catalog.resolve(&options.workflow)?.approval == ApprovalPolicy::CampaignDelegated,
            "campaign policy requires a campaign_delegated workflow"
        );
        Ok((policy, bytes))
    }
}

struct CampaignReviewer {
    run_id: String,
    policy_sha256: String,
}

impl HumanReviewer for CampaignReviewer {
    fn review(&mut self, target: &ApprovalTarget, _: &RenderedPlan) -> Result<HumanDecision> {
        ensure!(
            target.run_id == self.run_id,
            "campaign approval target run mismatch"
        );
        Ok(HumanDecision::ApproveDelegated {
            target: target.clone(),
            policy_sha256: self.policy_sha256.clone(),
        })
    }
}
