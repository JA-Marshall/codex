//! Fixed candidate evidence for explicitly selected verifier-only trials.

use std::collections::BTreeSet;

use anyhow::Result;
use anyhow::ensure;
use codex_lab::PlanRevision;
use serde::Deserialize;
use serde::Serialize;

use crate::artifact_input::digest;
use crate::reports::ImplementationReport;

/// Imported data, never authority or proof that verification passed. The host
/// binds its canonical bytes and candidate commit into the fresh approval target.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VerificationInput {
    schema_version: u32,
    candidate_commit: String,
    plan_sha256: String,
    source_run: String,
    source_phase_sha256: String,
    implementation_report: ImplementationReport,
}

impl VerificationInput {
    pub fn from_json(bytes: &[u8]) -> Result<Self> {
        ensure!(bytes.len() <= 8192, "verification input exceeds 8 KiB");
        let input: Self = serde_json::from_slice(bytes)?;
        ensure!(
            input.schema_version == 1,
            "unsupported verification input schema"
        );
        ensure!(
            !input.source_run.is_empty()
                && input.source_run.len() <= 64
                && input
                    .source_run
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_')),
            "invalid verification source run"
        );
        for hash in [&input.plan_sha256, &input.source_phase_sha256] {
            ensure!(
                hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
                "invalid verification input digest"
            );
        }
        ensure!(
            matches!(input.candidate_commit.len(), 40 | 64)
                && input
                    .candidate_commit
                    .bytes()
                    .all(|b| b.is_ascii_hexdigit()),
            "invalid verification candidate commit"
        );
        Ok(input)
    }

    pub(crate) fn validate(&self, plan: &PlanRevision, commit: &str) -> Result<()> {
        ensure!(
            self.candidate_commit == commit,
            "verification candidate commit changed"
        );
        ensure!(
            self.plan_sha256 == digest(&plan.canonical_json()?),
            "verification plan changed"
        );
        let completed = self
            .implementation_report
            .completed_steps
            .iter()
            .collect::<BTreeSet<_>>();
        ensure!(
            completed.len() == plan.steps.len()
                && completed.len() == self.implementation_report.completed_steps.len()
                && plan.steps.iter().all(|step| completed.contains(&step.id)),
            "imported implementation report must cover exactly the approved steps"
        );
        Ok(())
    }

    pub(crate) fn bytes(&self) -> Result<Vec<u8>> {
        Ok(serde_json::to_vec(self)?)
    }

    pub(crate) fn report(&self) -> ImplementationReport {
        self.implementation_report.clone()
    }
}

#[cfg(test)]
#[path = "verification_input_tests.rs"]
mod tests;
