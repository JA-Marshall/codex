use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::path::PathBuf;

use serde::Deserialize;
use serde::Serialize;

use crate::LabError;
use crate::Result;
use crate::RoleSelection;
use crate::digest_bytes;

pub const MAX_INSTRUCTION_BYTES: usize = 12 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SkillSource {
    path: String,
    sha256: String,
}

impl SkillSource {
    pub(crate) fn validate(&self) -> Result<()> {
        if self.path.is_empty()
            || self.path.contains(['\\', ':'])
            || self
                .path
                .split('/')
                .any(|part| matches!(part, "" | "." | ".."))
        {
            return Err(LabError::Invalid(
                "skill paths must be local relative directories using forward slashes".into(),
            ));
        }
        if self.sha256.len() != 64
            || !self
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(LabError::Invalid(
                "skill sha256 must be 64 lowercase hexadecimal characters".into(),
            ));
        }
        Ok(())
    }

    pub(crate) fn snapshot(&self, base: &Path, selector: &str) -> Result<InstructionSnapshot> {
        self.validate()?;
        let base = base.canonicalize()?;
        let path = base.join(&self.path).join("SKILL.md").canonicalize()?;
        if !path.starts_with(&base) {
            return Err(LabError::Invalid(format!(
                "skill {selector} resolves outside the catalog base"
            )));
        }
        let file = File::open(&path)?;
        if !file.metadata()?.is_file() {
            return Err(LabError::Invalid(format!("skill {selector} is not a file")));
        }
        let mut bytes = Vec::new();
        file.take((MAX_INSTRUCTION_BYTES + 1) as u64)
            .read_to_end(&mut bytes)?;
        if bytes.is_empty() || bytes.len() > MAX_INSTRUCTION_BYTES {
            return Err(LabError::Invalid(format!(
                "skill {selector} must contain between 1 and {MAX_INSTRUCTION_BYTES} bytes"
            )));
        }
        if digest_bytes(&bytes) != self.sha256 {
            return Err(LabError::Invalid(format!(
                "skill {selector} content hash mismatch"
            )));
        }
        let content = String::from_utf8(bytes)
            .map_err(|_| LabError::Invalid(format!("skill {selector} is not UTF-8")))?;
        Ok(InstructionSnapshot {
            selector: selector.to_owned(),
            path,
            sha256: self.sha256.clone(),
            content,
        })
    }
}

/// Immutable, content-pinned local instruction bytes. The later Codex adapter
/// must still discover the skill and verify its exact injection without truncation.
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct InstructionSnapshot {
    selector: String,
    path: PathBuf,
    sha256: String,
    content: String,
}

impl InstructionSnapshot {
    pub fn selector(&self) -> &str {
        &self.selector
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }

    pub fn content(&self) -> &str {
        &self.content
    }
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct RoleInstructions {
    pub planner: InstructionSnapshot,
    pub executor: InstructionSnapshot,
    pub verifier: InstructionSnapshot,
}

impl RoleInstructions {
    /// Check binding after composing roles; snapshots cannot be constructed from
    /// untrusted serialized data or mutated in place.
    pub fn validate(&self, roles: &RoleSelection) -> Result<()> {
        for (snapshot, selector) in [
            (&self.planner, &roles.planner),
            (&self.executor, &roles.executor),
            (&self.verifier, &roles.verifier),
        ] {
            if snapshot.selector() != selector
                || snapshot.content().is_empty()
                || snapshot.content().len() > MAX_INSTRUCTION_BYTES
                || digest_bytes(snapshot.content().as_bytes()) != snapshot.sha256()
            {
                return Err(LabError::Invalid(format!(
                    "instruction snapshot does not match role selector {selector}"
                )));
            }
        }
        Ok(())
    }
}
