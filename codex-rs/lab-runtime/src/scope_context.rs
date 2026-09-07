//! Conservative rendered-fragment bounds for the upstream permission formatters.

use std::path::Path;

use anyhow::Result;
use anyhow::bail;
use anyhow::ensure;
use codex_core_api::Config;
use codex_protocol::models::PermissionProfile;
use codex_protocol::permissions::FileSystemAccessMode;
use codex_protocol::permissions::FileSystemPath;
use codex_protocol::permissions::FileSystemSpecialPath;

use crate::context::MAX_PHASE_FRAGMENT_BYTES;

pub(crate) fn validate(
    config: &Config,
    profile: &PermissionProfile,
    instructions: &str,
    repository: &Path,
) -> Result<()> {
    // The complete developer fragment (role plus scope) is checked again by
    // validate_phase_context. This check also covers startup-only preflight.
    ensure!(
        instructions.len() <= MAX_PHASE_FRAGMENT_BYTES,
        "task scope instructions exceed rendered context bound"
    );
    let custom = config
        .model_catalog
        .as_ref()
        .and_then(|catalog| catalog.models.first())
        .and_then(|model| model.model_messages.as_ref())
        .map_or(0, |messages| {
            [
                messages
                    .approvals
                    .as_ref()
                    .and_then(|value| value.never.as_deref()),
                messages
                    .permissions
                    .as_ref()
                    .and_then(|value| value.read_only.as_deref()),
                messages
                    .permissions
                    .as_ref()
                    .and_then(|value| value.workspace_write.as_deref()),
            ]
            .into_iter()
            .flatten()
            .map(str::len)
            .sum::<usize>()
        });
    // Single local environment only: reserve 1 KiB for outer markers, date,
    // shell and filesystem wrappers. Cwd also appears in workspace_roots.
    let mut environment = 1024 + 2 * xml_bytes(&repository.to_string_lossy())?;
    // Never approval, no network/proxy/request-permissions/prefix sections.
    // This reserve exceeds the current default text and its section markers;
    // custom catalog messages are charged in addition, never substituted away.
    let mut permissions = 1024 + custom;
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
        // 96 bytes covers <entry>, access/escalatable attributes, path/special
        // tags and closing tags. Explicit paths occur once in the XML profile.
        environment += 96 + xml_bytes(&path)?;
        if matches!(
            entry.access,
            FileSystemAccessMode::Write | FileSystemAccessMode::Deny
        ) {
            // The human-readable permissions fragment repeats these roots as
            // backtick-delimited lists, with at most 32 syntax bytes per path.
            permissions += 32 + path.len();
        }
    }
    ensure!(
        environment <= MAX_PHASE_FRAGMENT_BYTES && permissions <= MAX_PHASE_FRAGMENT_BYTES,
        "task scope rendered context exceeds 8192-byte fragment bound (environment {environment}, permissions {permissions})"
    );
    Ok(())
}

fn xml_bytes(text: &str) -> Result<usize> {
    ensure!(
        !text.chars().any(char::is_control),
        "task scope context path contains control characters"
    );
    Ok(text
        .chars()
        .map(|character| match character {
            '&' => 5,
            '<' | '>' => 4,
            '"' | '\'' => 6,
            _ => character.len_utf8(),
        })
        .sum())
}

#[cfg(test)]
#[path = "scope_context_tests.rs"]
mod tests;
