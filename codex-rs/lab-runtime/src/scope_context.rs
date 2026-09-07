//! Path validation for the upstream permission and environment formatters.

use std::path::Path;

use anyhow::Result;
use anyhow::bail;
use anyhow::ensure;
use codex_protocol::models::PermissionProfile;
use codex_protocol::permissions::FileSystemPath;
use codex_protocol::permissions::FileSystemSpecialPath;

pub(crate) fn validate(profile: &PermissionProfile, repository: &Path) -> Result<()> {
    validate_path(&repository.to_string_lossy())?;
    for entry in profile.file_system_sandbox_policy().entries {
        let path = match entry.path {
            FileSystemPath::Path { path } => path.inferred_native_path_string(),
            FileSystemPath::Special {
                value: FileSystemSpecialPath::Minimal,
            } => ":minimal".to_owned(),
            FileSystemPath::Special { .. } | FileSystemPath::GlobPattern { .. } => {
                bail!("unsupported task scope context path")
            }
        };
        validate_path(&path)?;
    }
    Ok(())
}

fn validate_path(text: &str) -> Result<()> {
    ensure!(
        !text.chars().any(char::is_control),
        "task scope context path contains control characters"
    );
    Ok(())
}

#[cfg(test)]
#[path = "scope_context_tests.rs"]
mod tests;
