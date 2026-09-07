//! Repository-scoped advisory lock, held by every lab launch until shutdown.

use std::fs::File;
use std::fs::OpenOptions;
use std::io::ErrorKind;
use std::path::Path;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_protocol::permissions::FileSystemSandboxPolicy;

use crate::PhaseAccess;
use crate::git_evidence::repository_git_directory;

pub(crate) async fn acquire(repository: &Path) -> Result<File> {
    let repository = repository.canonicalize()?;
    let directory = repository_git_directory(&repository).await?;
    let path = directory.join("codex-lab-launch.lock");
    let policy = FileSystemSandboxPolicy::from_legacy_sandbox_policy_for_cwd(
        &PhaseAccess::WorkspaceWrite.policy(),
        &repository,
    );
    ensure!(
        !policy.can_write_local_path_with_cwd(&path, &repository),
        "launch lock would be model-writable"
    );
    match std::fs::symlink_metadata(&path) {
        Ok(metadata) => ensure!(
            metadata.is_file() && !metadata.file_type().is_symlink(),
            "invalid launch lock file"
        ),
        Err(error) if error.kind() == ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&path)?;
    file.try_lock()
        .context("another lab host owns this repository, or its launch lock is unavailable")?;
    // Never unlink: replacing a still-open inode would permit a second host.
    // The kernel releases the lock on normal exit or process death.
    Ok(file)
}
