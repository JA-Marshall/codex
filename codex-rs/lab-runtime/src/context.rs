use anyhow::Result;
use anyhow::ensure;
use codex_extension_api::SkillInvocationContributor;

/// Explicitly opts the restricted host out of legacy skill discovery. The role
/// instructions are already frozen and supplied through developer instructions.
pub struct ProceduralInstructionsOnly;

impl SkillInvocationContributor for ProceduralInstructionsOnly {
    fn requires_host_skill_discovery(&self) -> bool {
        false
    }
}

/// Require usable phase inputs without imposing a harness context-size limit.
/// The selected model and upstream runtime govern context capacity and compaction.
pub fn validate_phase_context(instructions: &str, prompt: &str) -> Result<()> {
    ensure!(
        !instructions.trim().is_empty(),
        "phase instructions are empty"
    );
    ensure!(!prompt.trim().is_empty(), "phase prompt is empty");
    Ok(())
}
