//! Candidate evidence includes ignored files, metadata and newly introduced aliases.

use std::collections::BTreeMap;
use std::collections::BTreeSet;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;

use anyhow::Result;
use anyhow::ensure;
use sha2::Digest;

use crate::task_scope::protected_component;

#[derive(PartialEq, Eq)]
struct Entry {
    directory: bool,
    mode: u32,
    digest: String,
}

#[cfg(test)]
#[path = "scope_audit_tests.rs"]
mod tests;

pub(crate) struct CandidateSnapshot(BTreeMap<PathBuf, Entry>);

impl CandidateSnapshot {
    pub fn capture(repository: &Path) -> Result<Self> {
        let mut entries = BTreeMap::new();
        let mut pending = vec![PathBuf::new()];
        let mut bytes = 0_u64;
        while let Some(relative) = pending.pop() {
            ensure!(
                entries.len() < 100_000,
                "task scope candidate exceeds entry limit"
            );
            let path = repository.join(&relative);
            let metadata = std::fs::symlink_metadata(&path)?;
            ensure!(
                !metadata.file_type().is_symlink(),
                "task scope rejects symlink alias: {}",
                path.display()
            );
            ensure!(
                metadata.is_dir() || metadata.is_file(),
                "task scope rejects special file: {}",
                path.display()
            );
            #[cfg(unix)]
            let mode = {
                use std::os::unix::fs::MetadataExt;
                ensure!(
                    !metadata.is_file() || metadata.nlink() == 1,
                    "task scope rejects hardlink alias: {}",
                    path.display()
                );
                metadata.mode()
            };
            #[cfg(not(unix))]
            let mode = u32::from(metadata.permissions().readonly());
            let mut hash = sha2::Sha256::new();
            if metadata.is_dir() {
                for child in std::fs::read_dir(&path)? {
                    pending.push(relative.join(child?.file_name()));
                }
            } else {
                let mut file = File::open(&path)?;
                let mut buffer = [0_u8; 32768];
                loop {
                    let count = file.read(&mut buffer)?;
                    if count == 0 {
                        break;
                    }
                    bytes += count as u64;
                    ensure!(
                        bytes <= 1024 * 1024 * 1024,
                        "task scope candidate exceeds byte limit"
                    );
                    hash.update(&buffer[..count]);
                }
            }
            entries.insert(
                relative,
                Entry {
                    directory: metadata.is_dir(),
                    mode,
                    digest: format!("{:x}", hash.finalize()),
                },
            );
        }
        Ok(Self(entries))
    }

    pub fn changed_paths(&self, after: &Self) -> BTreeSet<PathBuf> {
        self.0
            .keys()
            .chain(after.0.keys())
            .filter(|path| self.0.get(*path) != after.0.get(*path))
            .cloned()
            .collect()
    }

    pub fn protected_paths(&self, repository: &Path, roots: &[PathBuf]) -> BTreeSet<PathBuf> {
        let mut protected = BTreeSet::new();
        for (relative, value) in &self.0 {
            let path = repository.join(relative);
            if roots.iter().any(|root| path.starts_with(root)) {
                if relative
                    .file_name()
                    .is_some_and(|name| protected_component(&name.to_string_lossy()))
                {
                    protected.insert(path.clone());
                }
                if value.directory {
                    for name in [
                        ".git",
                        ".codex",
                        ".agents",
                        ".openai",
                        "AGENTS.md",
                        "TASK.md",
                        "CONTRACT.md",
                    ] {
                        protected.insert(path.join(name));
                    }
                }
            }
        }
        protected
    }
}
