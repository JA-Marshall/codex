//! Bounded read-only artifact access. No artifact can restore runtime authority.

use std::fs::File;
use std::io::Read;
use std::path::Path;

use anyhow::Result;
use anyhow::ensure;
use sha2::Digest;

pub(crate) const MAX_ARTIFACT_BYTES: usize = 8 * 1024 * 1024;

pub(crate) fn digest(bytes: &[u8]) -> String {
    format!("{:x}", sha2::Sha256::digest(bytes))
}

pub(crate) fn read_artifact(root: &Path, relative: &str, limit: usize) -> Result<Vec<u8>> {
    ensure!(relative.len() <= 256, "artifact path exceeds limit");
    let mut path = root.to_owned();
    for component in relative.split('/') {
        ensure!(
            !component.is_empty()
                && component != "."
                && component != ".."
                && component
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b)),
            "artifact reference must be a safe relative path"
        );
        path.push(component);
        ensure!(
            !std::fs::symlink_metadata(&path)?.file_type().is_symlink(),
            "artifact symlinks are unsupported"
        );
    }
    ensure!(
        path.canonicalize()?.starts_with(root),
        "artifact escapes run"
    );
    let file = File::open(path)?;
    let metadata = file.metadata()?;
    ensure!(
        metadata.is_file() && metadata.len() <= limit as u64,
        "artifact exceeds file limit"
    );
    let mut bytes = Vec::new();
    file.take(limit as u64 + 1).read_to_end(&mut bytes)?;
    ensure!(bytes.len() <= limit, "artifact grew beyond file limit");
    Ok(bytes)
}
