//! Read-only, bounded Git evidence using Git's own diff semantics.

use std::ffi::OsString;
use std::path::Path;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use anyhow::Context;
use anyhow::bail;
use tokio::io::AsyncRead;
use tokio::io::AsyncReadExt;
use tokio::process::Command;
use tokio::time::Instant;
use tokio::time::timeout_at;

const MAX_CAPTURE_BYTES: usize = 8 * 1024 * 1024;
const MAX_DIAGNOSTIC_BYTES: usize = 64 * 1024;
const NULL_PATH: &str = if cfg!(windows) { "NUL" } else { "/dev/null" };

/// Exact Git patch and file counts relative to one pinned initial commit.
///
/// Ignored untracked files are excluded by Git's standard ignore rules. Binary
/// changes are retained in Git's binary patch format. Capture requires a quiescent
/// worktree; this adapter neither locks user files nor controls agent lifecycles.
#[derive(Debug)]
pub struct GitEvidence {
    pub base_commit: String,
    pub final_commit: String,
    pub diff: Vec<u8>,
    pub files_changed: usize,
    pub untracked_files: Vec<String>,
}

/// Requires the exact repository root, matching HEAD, and a clean initial tree.
///
/// Both tracked and non-ignored untracked changes reject the baseline. This never
/// creates a commit, modifies the index, resets files, or initializes Git metadata.
pub async fn verify_git_baseline(root: &Path, pinned_commit: &str) -> anyhow::Result<()> {
    validate_commit(pinned_commit)?;
    let mut capture = Capture::new(root).await?;
    capture.verify_head(pinned_commit).await?;
    let status = capture
        .run(
            &["status", "--porcelain=v1", "--untracked-files=all", "-z"],
            ExitPolicy::Success,
        )
        .await?;
    if !status.is_empty() {
        bail!("experimental repository must start clean, including non-ignored untracked files");
    }
    Ok(())
}

pub(crate) async fn repository_git_directory(root: &Path) -> anyhow::Result<PathBuf> {
    let mut capture = Capture::new(root).await?;
    let directory = capture.run(&["rev-parse", "--absolute-git-dir"], ExitPolicy::Success).await?;
    Ok(PathBuf::from(std::str::from_utf8(&directory)?.trim_end_matches('\n')).canonicalize()?)
}

/// Captures tracked and non-ignored untracked changes against the pinned commit.
///
/// A changed HEAD, unsupported untracked entry, timeout, or size excess rejects
/// capture instead of returning an incomplete patch as complete evidence.
pub async fn capture_git_diff(root: &Path, pinned_commit: &str) -> anyhow::Result<GitEvidence> {
    validate_commit(pinned_commit)?;
    let mut capture = Capture::new(root).await?;
    capture.verify_head(pinned_commit).await?;
    let names = capture
        .run(
            &[
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-only",
                "-z",
                pinned_commit,
                "--",
            ],
            ExitPolicy::Success,
        )
        .await?;
    let tracked_count = names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
        .count();
    let mut diff = capture
        .run(
            &[
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--binary",
                "--no-renames",
                pinned_commit,
                "--",
            ],
            ExitPolicy::Success,
        )
        .await?;
    let untracked = capture
        .run(
            &["ls-files", "--others", "--exclude-standard", "-z"],
            ExitPolicy::Success,
        )
        .await?;
    let mut untracked_files = Vec::new();
    for name in untracked
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let name = std::str::from_utf8(name).context("untracked evidence path is not UTF-8")?;
        if name.is_empty()
            || name.contains(['\\', ':'])
            || name.chars().any(char::is_control)
            || name
                .split('/')
                .any(|part| matches!(part, "" | "." | ".." | ".git"))
        {
            bail!("unsupported untracked evidence path");
        }
        let path = capture.root.join(name);
        let metadata = std::fs::symlink_metadata(&path)?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            bail!("untracked evidence entries must be regular files");
        }
        if !path.canonicalize()?.starts_with(&capture.root) {
            bail!("untracked evidence path resolves outside the repository");
        }
        let patch = capture
            .run(
                &[
                    "diff",
                    "--no-index",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--binary",
                    "--no-renames",
                    "--",
                    NULL_PATH,
                    name,
                ],
                ExitPolicy::SuccessOrDifference,
            )
            .await?;
        diff.extend_from_slice(&patch);
        untracked_files.push(name.to_string());
    }
    capture.verify_head(pinned_commit).await?;
    Ok(GitEvidence {
        base_commit: pinned_commit.to_string(),
        final_commit: pinned_commit.to_string(),
        files_changed: tracked_count + untracked_files.len(),
        diff,
        untracked_files,
    })
}

fn validate_commit(commit: &str) -> anyhow::Result<()> {
    if !matches!(commit.len(), 40 | 64) || !commit.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        bail!("Git evidence requires a full pinned hexadecimal commit identifier");
    }
    Ok(())
}

enum ExitPolicy {
    Success,
    SuccessOrDifference,
}

struct Capture {
    root: PathBuf,
    deadline: Instant,
    remaining: usize,
    filter_overrides: Vec<OsString>,
}

impl Capture {
    async fn new(root: &Path) -> anyhow::Result<Self> {
        let root = root.canonicalize()?;
        let mut capture = Self {
            root,
            deadline: Instant::now() + Duration::from_secs(30),
            remaining: MAX_CAPTURE_BYTES,
            filter_overrides: Vec::new(),
        };
        let top_level = capture
            .run(&["rev-parse", "--show-toplevel"], ExitPolicy::Success)
            .await?;
        let top_level = Path::new(std::str::from_utf8(&top_level)?.trim_end_matches(['\n', '\r']))
            .canonicalize()?;
        if top_level != capture.root {
            bail!("Git evidence requires the exact repository root");
        }
        // --no-ext-diff and --no-textconv do not disable clean/process filters.
        // Discover every configured filter before diff/status and override it.
        let filters = capture
            .run(
                &[
                    "config",
                    "--null",
                    "--name-only",
                    "--get-regexp",
                    "^filter\\..*\\.(clean|smudge|process|required)$",
                ],
                ExitPolicy::SuccessOrDifference,
            )
            .await?;
        for key in filters
            .split(|byte| *byte == 0)
            .filter(|key| !key.is_empty())
        {
            let key =
                std::str::from_utf8(key).context("Git filter configuration key is not UTF-8")?;
            let value = if key.ends_with(".required") {
                "false"
            } else {
                ""
            };
            capture.filter_overrides.push(OsString::from("-c"));
            capture
                .filter_overrides
                .push(OsString::from(format!("{key}={value}")));
        }
        // Nested repositories have separate local filters and process policies.
        // The first restricted driver does not claim to control those contexts.
        let index = capture
            .run(&["ls-files", "--stage", "-z"], ExitPolicy::Success)
            .await?;
        if index
            .split(|byte| *byte == 0)
            .any(|entry| entry.starts_with(b"160000 "))
        {
            bail!("Git evidence does not support repositories containing submodules");
        }
        Ok(capture)
    }

    async fn verify_head(&mut self, pinned_commit: &str) -> anyhow::Result<()> {
        let head = self
            .run(
                &["rev-parse", "--verify", "HEAD^{commit}"],
                ExitPolicy::Success,
            )
            .await?;
        if !std::str::from_utf8(&head)?
            .trim()
            .eq_ignore_ascii_case(pinned_commit)
        {
            bail!("repository HEAD differs from the pinned experiment commit");
        }
        Ok(())
    }

    async fn run(&mut self, args: &[&str], policy: ExitPolicy) -> anyhow::Result<Vec<u8>> {
        let mut command = Command::new("git");
        command
            .current_dir(&self.root)
            .args([
                "--no-pager",
                "--no-optional-locks",
                "-c",
                "safe.bareRepository=explicit",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.untrackedCache=false",
                "-c",
                "core.quotePath=true",
                "-c",
                "diff.suppressBlankEmpty=false",
            ])
            .args([
                "-c",
                &format!("core.hooksPath={NULL_PATH}"),
                "-c",
                &format!("core.attributesFile={NULL_PATH}"),
            ])
            .args(&self.filter_overrides);
        if args.first() == Some(&"diff") {
            // Pin the patch representation independently of local diff settings.
            // These flags apply equally to tracked and --no-index added files.
            command.arg("diff");
            // Git selects no-index mode before parsing ordinary diff options.
            // Keep its selector first so /dev/null is not treated as a repo path.
            if args.contains(&"--no-index") {
                command.arg("--no-index");
            }
            command
                .args([
                    "--no-color",
                    "--src-prefix=a/",
                    "--dst-prefix=b/",
                    "--unified=3",
                    "--inter-hunk-context=0",
                    "--diff-algorithm=myers",
                    "--no-indent-heuristic",
                    "-O",
                    NULL_PATH,
                ])
                .args(
                    args.iter()
                        .skip(1)
                        .filter(|argument| **argument != "--no-index"),
                );
        } else {
            command.args(args);
        }
        command
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", NULL_PATH)
            .env("GIT_NO_LAZY_FETCH", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        for name in [
            "GIT_DIR",
            "GIT_COMMON_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_PARAMETERS",
            "GIT_EXTERNAL_DIFF",
            "GIT_DIFF_OPTS",
        ] {
            command.env_remove(name);
        }
        codex_protocol::shell_environment::scrub_non_inheritable_env_vars(command.as_std_mut());
        let mut child = command
            .spawn()
            .context("start read-only Git evidence command")?;
        let stdout = child.stdout.take().context("missing Git stdout")?;
        let stderr = child.stderr.take().context("missing Git stderr")?;
        let (output, _diagnostics, status) = timeout_at(self.deadline, async {
            tokio::try_join!(
                read_bounded(stdout, self.remaining),
                read_bounded(stderr, MAX_DIAGNOSTIC_BYTES),
                child.wait(),
            )
        })
        .await
        .context("Git evidence exceeded its 30 second capture deadline")??;
        self.remaining -= output.len();
        if !(status.success()
            || matches!(policy, ExitPolicy::SuccessOrDifference) && status.code() == Some(1))
        {
            // Raw diagnostics may contain paths or configuration values. Callers
            // receive the exit status without automatically collecting that data.
            bail!("Git evidence command failed with status {status}");
        }
        Ok(output)
    }
}

async fn read_bounded(reader: impl AsyncRead + Unpin, limit: usize) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .await?;
    if bytes.len() > limit {
        return Err(std::io::Error::other(
            "Git evidence exceeds the bounded capture size",
        ));
    }
    Ok(bytes)
}
