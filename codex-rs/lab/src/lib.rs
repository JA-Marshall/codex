//! Experimental workflow data and approval contracts, independent of the Codex runtime.
//!
//! This crate does not intercept live Codex tools. Human decisions are trusted host
//! inputs; a future adapter must supply the authenticated boundary and enforce
//! admission for every tool, including concurrent work and child agents.

mod config;
mod instructions;
mod plan;
mod render;
mod run;
mod workflow;

pub use config::ApprovalPolicy;
pub use config::PlanConfig;
pub use config::Renderer;
pub use config::ResolvedWorkflow;
pub use config::RoleSelection;
pub use config::WorkflowCatalog;
pub use instructions::InstructionSnapshot;
pub use instructions::MAX_INSTRUCTION_BYTES;
pub use instructions::RoleInstructions;
pub use plan::PlanCriterion;
pub use plan::PlanRevision;
pub use plan::PlanStep;
pub use render::JsonRenderer;
pub use render::MarkdownRenderer;
pub use render::PlanRenderer;
pub use render::RenderedPlan;
pub use run::LabRun;
pub use run::ModelMetadata;
pub use run::RepositoryMetadata;
pub use run::RunSpec;
pub use workflow::ActionKind;
pub use workflow::ApprovalTarget;
pub use workflow::StepProgress;
pub use workflow::StepStatus;
pub use workflow::VerificationEvidence;
pub use workflow::WorkflowSnapshot;
pub use workflow::WorkflowState;

/// Validation, recording or decoding failure. No error grants execution authority.
#[derive(Debug, thiserror::Error)]
pub enum LabError {
    #[error("invalid laboratory input: {0}")]
    Invalid(String),
    #[error("laboratory recording failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("invalid JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("invalid TOML: {0}")]
    Toml(#[from] toml::de::Error),
}

pub type Result<T> = std::result::Result<T, LabError>;

fn digest_bytes(bytes: &[u8]) -> String {
    use sha2::Digest;
    format!("{:x}", sha2::Sha256::digest(bytes))
}
