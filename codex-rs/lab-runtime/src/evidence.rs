//! Host-owned, bounded, write-once evidence for one live run.

#[cfg(unix)]
use std::fs::File;
use std::fs::OpenOptions;
use std::io;
use std::io::Write;
use std::path::Path;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::Serialize;

const MAX_RECORD_BYTES: usize = 8 * 1024 * 1024;

/// Writes evidence beneath an existing, host-protected run artifact directory.
///
/// Callers choose explicit, non-secret metadata projections; this store does not
/// inspect the environment, redact credentials, or decide whether evidence proves
/// success. Any failed write permanently closes this instance to further writes.
/// Partial files remain for diagnosis and never constitute resumable authority.
pub struct EvidenceStore {
    directory: PathBuf,
    failed: Mutex<bool>,
}

impl EvidenceStore {
    /// Creates a fresh `evidence` directory; existing evidence is never reopened.
    pub fn new(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref().canonicalize()?;
        if !root.is_dir() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "artifact root is not a directory",
            ));
        }
        let directory = root.join("evidence");
        std::fs::create_dir(&directory)?;
        #[cfg(unix)]
        File::open(&root)?.sync_all()?;
        Ok(Self {
            directory,
            failed: Mutex::new(false),
        })
    }

    /// Serializes one record with a final newline, bounded before opening a file.
    pub fn write_json(&self, name: &str, value: &impl Serialize) -> io::Result<PathBuf> {
        self.write_record(name, || {
            let mut buffer = BoundedBuffer(Vec::new());
            serde_json::to_writer_pretty(&mut buffer, value).map_err(io::Error::other)?;
            buffer.write_all(b"\n")?;
            Ok(buffer.0)
        })
    }

    /// Writes exact bytes with no truncation or newline transformation.
    pub fn write_bytes(&self, name: &str, bytes: &[u8]) -> io::Result<PathBuf> {
        self.write_record(name, || {
            if bytes.len() > MAX_RECORD_BYTES {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "evidence exceeds the 8 MiB record limit",
                ));
            }
            Ok(bytes.to_vec())
        })
    }

    fn write_record(
        &self,
        name: &str,
        encode: impl FnOnce() -> io::Result<Vec<u8>>,
    ) -> io::Result<PathBuf> {
        let mut failed = self
            .failed
            .lock()
            .map_err(|_| io::Error::other("evidence store lock poisoned"))?;
        if *failed {
            return Err(io::Error::other(
                "evidence store is closed after a previous failure",
            ));
        }
        let result = (|| {
            let stem = name
                .split('.')
                .next()
                .unwrap_or_default()
                .to_ascii_uppercase();
            if name.is_empty()
                || name.len() > 128
                || !name
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte))
                || !name.as_bytes()[0].is_ascii_alphanumeric()
                || name.ends_with('.')
                || matches!(
                    stem.as_str(),
                    "CON"
                        | "PRN"
                        | "AUX"
                        | "NUL"
                        | "COM1"
                        | "COM2"
                        | "COM3"
                        | "COM4"
                        | "COM5"
                        | "COM6"
                        | "COM7"
                        | "COM8"
                        | "COM9"
                        | "LPT1"
                        | "LPT2"
                        | "LPT3"
                        | "LPT4"
                        | "LPT5"
                        | "LPT6"
                        | "LPT7"
                        | "LPT8"
                        | "LPT9"
                )
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "evidence name must be a simple portable filename",
                ));
            }
            let bytes = encode()?;
            let path = self.directory.join(name);
            let mut file = OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&path)?;
            file.write_all(&bytes)?;
            file.sync_all()?;
            // Windows sync_all flushes file data. Live crash-resume and portable
            // atomic directory publication are deliberately not promised here.
            #[cfg(unix)]
            File::open(&self.directory)?.sync_all()?;
            Ok(path)
        })();
        if result.is_err() {
            *failed = true;
        }
        result
    }
}

struct BoundedBuffer(Vec<u8>);

impl Write for BoundedBuffer {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > MAX_RECORD_BYTES - self.0.len() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "evidence exceeds the 8 MiB record limit",
            ));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
