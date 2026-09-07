//! Restricted experimental host; the upstream runtime owns model and tool execution.

mod amendment_tool;
mod artifact_input;
mod authority;
mod backend;
mod bootstrap;
mod command_receipts;
mod context;
mod driver;
mod driver_preparation;
mod evidence;
mod git_evidence;
mod preflight;
mod prepared;
mod prepared_journal;
mod prepared_launch;
mod prepared_lock;
mod reports;
mod repository_tools;
mod review;
mod settings;

#[cfg(test)]
#[path = "../tests/authority_support/mod.rs"]
mod authority_support;

pub use authority::Phase;
pub use authority::PhaseGate;
pub use authority::RunAuthority;
pub use backend::CodexBackend;
pub use backend::PhaseOutput;
pub use backend::PhaseRequest;
pub use bootstrap::PreparedRuntime;
pub use bootstrap::restricted_overrides;
pub use bootstrap::restricted_requirements;
pub use context::ProceduralInstructionsOnly;
pub use context::validate_phase_context;
pub use driver::RunOptions;
pub use driver::RunResult;
pub use prepared::PreparedRunResult;
pub use prepared_launch::execute_run;
pub use prepared_launch::prepare_run;
pub use prepared_launch::run_prepared;
pub use evidence::EvidenceStore;
pub use git_evidence::GitEvidence;
pub use git_evidence::capture_git_diff;
pub use git_evidence::verify_git_baseline;
pub use preflight::PhaseAccess;
pub use preflight::RuntimePaths;
pub use preflight::validate_model_catalog;
pub use preflight::validate_runtime_config;
pub use repository_tools::RepositoryTools;
pub use repository_tools::install_repository_tools;
pub use review::HumanDecision;
pub use review::HumanReviewer;
pub use review::TerminalReviewer;
pub use review::parse_decision;
