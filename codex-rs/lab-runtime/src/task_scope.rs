//! Immutable campaign write authority, compiled to upstream managed permissions.

use std::path::Path;
use std::path::PathBuf;

use anyhow::Context;
use anyhow::Result;
use anyhow::ensure;
use codex_core_api::Config;
use codex_protocol::models::ManagedFileSystemPermissions;
use codex_protocol::models::PermissionProfile;
use codex_protocol::permissions::FileSystemAccessMode;
use codex_protocol::permissions::FileSystemPath;
use codex_protocol::permissions::FileSystemSandboxEntry;
use codex_protocol::permissions::FileSystemSpecialPath;
use codex_protocol::permissions::NetworkSandboxPolicy;
use codex_utils_absolute_path::AbsolutePathBuf;
use serde::Deserialize;
use serde::Serialize;
use tempfile::TempDir;

use crate::Phase;
use crate::PhaseAccess;
use crate::PreparedRuntime;
use crate::RuntimePaths;
use crate::artifact_input::digest;
use crate::scope_audit::CandidateSnapshot;

#[derive(Debug)]
pub(crate) struct ScopeBlocked(pub anyhow::Error);

impl std::fmt::Display for ScopeBlocked {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "task scope blocked: {:#}", self.0)
    }
}

impl std::error::Error for ScopeBlocked {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(self.0.as_ref())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct TaskScope {
    schema_version: u32,
    write_paths: Vec<String>,
    #[serde(default)]
    deny_read_paths: Vec<PathBuf>,
    #[serde(default)]
    read_paths: Vec<PathBuf>,
}

pub(crate) struct BoundTaskScope {
    pub definition: TaskScope,
    pub sha256: String,
    repository: PathBuf,
    roots: Vec<PathBuf>,
    denied: Vec<PathBuf>,
}

impl TaskScope {
    pub fn bind(self, paths: &RuntimePaths) -> Result<BoundTaskScope> {
        ensure!(cfg!(target_os = "linux"), "task scope requires Linux");
        ensure!(self.schema_version == 1, "unsupported task scope schema");
        ensure!(
            !self.write_paths.is_empty()
                && self.write_paths.len() <= 16
                && self.write_paths.iter().map(String::len).sum::<usize>() <= 1024,
            "task scope requires 1..16 bounded write paths"
        );
        ensure!(
            self.deny_read_paths.len() <= 16,
            "too many task scope denied roots"
        );
        let mut roots = Vec::new();
        for relative in &self.write_paths {
            ensure!(
                !relative.is_empty()
                    && relative.len() <= 128
                    && relative.split('/').all(|part| !part.is_empty()
                        && part != "."
                        && part != ".."
                        && part
                            .bytes()
                            .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte))
                        && !protected_component(part)),
                "unsafe or protected task scope write path: {relative}"
            );
            let root = paths.repository().join(relative);
            ensure!(
                root.exists(),
                "task scope write roots must already exist: {relative}"
            );
            ensure!(
                root.canonicalize()? == root,
                "task scope path alias: {relative}"
            );
            ensure!(
                !roots
                    .iter()
                    .any(|other: &PathBuf| root.starts_with(other) || other.starts_with(&root)),
                "overlapping task scope write paths"
            );
            roots.push(root);
        }
        let mut denied = vec![
            paths.codex_home().to_path_buf(),
            paths.artifacts().to_path_buf(),
        ];
        for path in &self.deny_read_paths {
            ensure!(
                path.is_absolute() && path.is_dir() && path.canonicalize()? == *path,
                "task scope denied roots must be canonical existing absolute directories"
            );
            ensure!(
                !paths.repository().starts_with(path) && !path.starts_with(paths.repository()),
                "task scope denied root overlaps candidate"
            );
            denied.push(path.clone());
        }
        denied.sort();
        denied.dedup();
        ensure!(
            self.read_paths.len() <= 16,
            "too many task scope read roots"
        );
        for path in &self.read_paths {
            ensure!(
                path.is_absolute()
                    && path.is_dir()
                    && path.components().count() >= 3
                    && path.canonicalize()? == *path,
                "task scope read roots must be canonical existing specific absolute directories"
            );
            ensure!(
                !path.starts_with(paths.repository())
                    && !paths.repository().starts_with(path)
                    && !denied
                        .iter()
                        .any(|root| path.starts_with(root) || root.starts_with(path)),
                "task scope read root overlaps candidate or protected authority"
            );
        }
        CandidateSnapshot::capture(paths.repository())?;
        let sha256 = digest(&serde_json::to_vec(&self)?);
        Ok(BoundTaskScope {
            definition: self,
            sha256,
            repository: paths.repository().to_path_buf(),
            roots,
            denied,
        })
    }
}

impl BoundTaskScope {
    pub async fn validate_runtime(&self, runtime: &PreparedRuntime) -> Result<()> {
        for phase in [Phase::Research, Phase::Implementation, Phase::Verification] {
            let scoped = self.begin_phase(phase, runtime.config())?;
            let mut config = runtime.config().clone();
            scoped.configure(&mut config)?;
            let access = if phase == Phase::Research {
                PhaseAccess::ReadOnly
            } else {
                config.features.enable(codex_core_api::Feature::ShellTool)?;
                PhaseAccess::WorkspaceWrite
            };
            crate::preflight::validate_phase_config(
                &config,
                runtime.paths(),
                access,
                Some(&scoped.profile),
            )?;
            scoped.verify_sandbox(&config, &self.repository).await?;
        }
        Ok(())
    }

    pub fn begin_phase(&self, phase: Phase, config: &Config) -> Result<ScopedPhase> {
        let snapshot = CandidateSnapshot::capture(&self.repository)?;
        for root in &self.roots {
            ensure!(
                root.exists() && root.canonicalize()? == *root,
                "task scope root disappeared or became an alias"
            );
        }
        let scratch = tempfile::Builder::new()
            .prefix("codex-lab-task-")
            .tempdir()?;
        let scratch_path = scratch.path().canonicalize()?;
        ensure!(
            !scratch_path.starts_with(&self.repository)
                && !self
                    .denied
                    .iter()
                    .any(|root| scratch_path.starts_with(root) || root.starts_with(&scratch_path)),
            "task scope scratch overlaps protected roots"
        );
        let mut entries = vec![FileSystemSandboxEntry::new(
            FileSystemPath::Special {
                value: FileSystemSpecialPath::Minimal,
            },
            FileSystemAccessMode::Read,
        )];
        let mut read_paths = self.definition.read_paths.clone();
        read_paths.push(self.repository.clone());
        for helper in [
            config.codex_self_exe.as_ref(),
            config.codex_linux_sandbox_exe.as_ref(),
            config.main_execve_wrapper_exe.as_ref(),
        ]
        .into_iter()
        .flatten()
        {
            read_paths.push(helper.canonicalize()?);
        }
        read_paths.sort();
        read_paths.dedup();
        for path in &read_paths {
            ensure!(
                path.canonicalize()? == *path,
                "task scope read path became an alias"
            );
            ensure!(
                !self
                    .denied
                    .iter()
                    .any(|root| path.starts_with(root) || root.starts_with(path)),
                "task scope runtime read overlaps protected authority"
            );
            entries.push(entry(path, FileSystemAccessMode::Read)?);
        }
        let mut write_paths = Vec::new();
        if phase == Phase::Implementation {
            write_paths.extend(self.roots.iter().cloned());
        }
        if matches!(phase, Phase::Implementation | Phase::Verification) {
            write_paths.push(scratch_path.clone());
        }
        for path in &write_paths {
            entries.push(entry(path, FileSystemAccessMode::Write)?);
        }
        for path in &self.denied {
            entries.push(entry(path, FileSystemAccessMode::Deny)?);
        }
        // Protect instruction and VCS entries nested under an authorized directory,
        // including missing names that a model might otherwise introduce.
        for path in snapshot.protected_paths(&self.repository, &self.roots) {
            entries.push(entry(&path, FileSystemAccessMode::Read)?);
        }
        let profile = PermissionProfile::Managed {
            file_system: ManagedFileSystemPermissions::Restricted {
                entries,
                glob_scan_max_depth: None,
            },
            network: NetworkSandboxPolicy::Restricted,
        };
        let evidence = serde_json::json!({"schema_version":1,"scope_sha256":self.sha256,
            "task_write_paths":self.roots,
            "phase":phase,"candidate_write_paths":if phase == Phase::Implementation { self.roots.clone() } else { Vec::new() },
            "scratch":scratch_path,"deny_read_paths":self.denied,"read_paths":read_paths,"permission_profile":profile});
        ensure!(
            serde_json::to_vec(&evidence)?.len() < 12000,
            "scope permission evidence exceeds limit"
        );
        let scoped = ScopedPhase {
            scratch,
            snapshot,
            profile,
            evidence,
            write_paths,
        };
        crate::scope_context::validate(&scoped.profile, &self.repository)?;
        Ok(scoped)
    }

    pub fn audit(&self, phase: &ScopedPhase) -> Result<serde_json::Value> {
        let after = CandidateSnapshot::capture(&self.repository)?;
        let changed = phase.snapshot.changed_paths(&after);
        let violation = changed.iter().find(|path| {
            let absolute = self.repository.join(path);
            !phase
                .write_paths
                .iter()
                .any(|root| absolute.starts_with(root))
                || path
                    .components()
                    .any(|part| protected_component(&part.as_os_str().to_string_lossy()))
        });
        Ok(
            serde_json::json!({"scope_sha256":self.sha256,"candidate_unchanged":changed.is_empty(),
            "changed_paths":changed.len(),"authorized":violation.is_none(),"first_violation":violation}),
        )
    }
}

pub(crate) struct ScopedPhase {
    scratch: TempDir,
    snapshot: CandidateSnapshot,
    pub profile: PermissionProfile,
    pub evidence: serde_json::Value,
    write_paths: Vec<PathBuf>,
}

impl ScopedPhase {
    pub fn configure(&self, config: &mut Config) -> Result<()> {
        config
            .permissions
            .set_permission_profile(self.profile.clone())?;
        let scratch = self
            .scratch
            .path()
            .to_str()
            .context("scratch is not UTF-8")?;
        for (key, value) in [
            ("TMPDIR", scratch),
            ("CARGO_TARGET_DIR", scratch),
            ("CARGO_HOME", scratch),
            ("PYTHONDONTWRITEBYTECODE", "1"),
        ] {
            config
                .permissions
                .shell_environment_policy
                .r#set
                .insert(key.to_owned(), value.to_owned());
        }
        Ok(())
    }

    pub fn instructions(&self) -> String {
        format!(
            "\nFrozen task scope: implementation may write only {}. This phase may write candidate paths {}. Verification must leave the candidate unchanged. Use scratch {} for all build/test output. Plans and amendments cannot expand this authority. Report any scope blocker honestly.",
            self.evidence["task_write_paths"],
            self.evidence["candidate_write_paths"],
            self.scratch.path().display()
        )
    }

    pub async fn verify_sandbox(&self, config: &Config, repository: &Path) -> Result<()> {
        let helper = config
            .codex_linux_sandbox_exe
            .as_deref()
            .context("missing Linux sandbox helper")?;
        let mut command = tokio::process::Command::new(helper);
        command.arg("--sandbox-policy-cwd").arg(repository)
            .arg("--permission-profile").arg(serde_json::to_string(&self.profile)?)
            .args(["--", "/bin/sh", "-c", "test ! -w \"$1\" || exit 90; shift; for path do test -w \"$path\" || exit 91; done", "scope-preflight"])
            .arg(repository).args(&self.write_paths)
            .current_dir(repository).env_clear().env("PATH", "/usr/local/bin:/usr/bin:/bin")
            .stdin(std::process::Stdio::null()).kill_on_drop(true);
        let output = tokio::time::timeout(std::time::Duration::from_secs(30), command.output())
            .await
            .context("task scope sandbox preflight timed out")??;
        ensure!(
            output.status.success(),
            "task scope sandbox preflight failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        Ok(())
    }
}

fn entry(path: &Path, access: FileSystemAccessMode) -> Result<FileSystemSandboxEntry> {
    Ok(FileSystemSandboxEntry::new(
        FileSystemPath::from(AbsolutePathBuf::from_absolute_path(path)?),
        access,
    ))
}

pub(crate) fn protected_component(name: &str) -> bool {
    matches!(
        name.to_ascii_lowercase().as_str(),
        ".git" | ".codex" | ".agents" | ".openai" | "agents.md" | "task.md" | "contract.md"
    )
}

#[cfg(test)]
#[path = "task_scope_tests.rs"]
mod tests;
