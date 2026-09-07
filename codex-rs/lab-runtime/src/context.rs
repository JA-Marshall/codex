use anyhow::Result;
use anyhow::ensure;
use codex_extension_api::SkillInvocationContributor;

/// A conservative byte cap bounds each injected instruction or task fragment.
pub const MAX_PHASE_FRAGMENT_BYTES: usize = 8 * 1024;
pub const MAX_PHASE_CONTEXT_BYTES: usize = 16 * 1024;

/// Explicitly opts the restricted host out of legacy skill discovery. The role
/// instructions are already frozen and supplied through developer instructions.
pub struct ProceduralInstructionsOnly;

impl SkillInvocationContributor for ProceduralInstructionsOnly {
    fn requires_host_skill_discovery(&self) -> bool {
        false
    }
}

/// Validate frozen phase inputs before starting a thread. Oversized inputs are
/// rejected, never silently truncated or summarized by a representation adapter.
pub fn validate_phase_context(instructions: &str, prompt: &str) -> Result<()> {
    ensure!(
        !instructions.trim().is_empty(),
        "phase instructions are empty"
    );
    ensure!(!prompt.trim().is_empty(), "phase prompt is empty");
    ensure!(
        instructions.len() <= MAX_PHASE_FRAGMENT_BYTES,
        "phase instructions exceed the context byte limit"
    );
    ensure!(
        prompt.len() <= MAX_PHASE_FRAGMENT_BYTES,
        "phase prompt exceeds the context byte limit"
    );
    ensure!(
        instructions.len().saturating_add(prompt.len()) <= MAX_PHASE_CONTEXT_BYTES,
        "combined phase context exceeds the byte limit"
    );
    Ok(())
}
