use std::io::Write;
use std::path::Path;
use std::process::Command;
use std::process::Stdio;

use anyhow::Context;
use anyhow::bail;
use codex_lab_runtime::capture_git_diff;
use codex_lab_runtime::verify_git_baseline;
use pretty_assertions::assert_eq;
use tempfile::TempDir;

struct Repository {
    directory: TempDir,
    commit: String,
}

impl Repository {
    fn new() -> anyhow::Result<Self> {
        let directory = tempfile::tempdir()?;
        let root = directory.path();
        git(root, &["init", "-q", "--initial-branch=main"])?;
        git(root, &["config", "user.name", "Lab Tests"])?;
        git(root, &["config", "user.email", "lab-tests@example.invalid"])?;
        std::fs::write(root.join("tracked.txt"), b"before\n")?;
        std::fs::write(root.join(".gitignore"), b"*.ignored\n")?;
        git(root, &["add", "--all"])?;
        git(root, &["commit", "-qm", "baseline"])?;
        let commit = git(root, &["rev-parse", "HEAD"])?;
        Ok(Self { directory, commit })
    }
}

fn git(root: &Path, arguments: &[&str]) -> anyhow::Result<String> {
    let output = Command::new("git")
        .current_dir(root)
        .args(arguments)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env(
            "GIT_CONFIG_GLOBAL",
            if cfg!(windows) { "NUL" } else { "/dev/null" },
        )
        .output()?;
    if !output.status.success() {
        bail!(
            "fixture Git command failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Ok(String::from_utf8(output.stdout)?.trim().to_string())
}

#[tokio::test]
async fn captures_applicable_tracked_and_binary_untracked_patch_without_changing_index()
-> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    let initial_index = std::fs::read(root.join(".git/index"))?;
    std::fs::write(root.join("local.ignored"), b"excluded local build output")?;
    verify_git_baseline(root, &repository.commit).await?;
    std::fs::write(root.join("tracked.txt"), b"after\n")?;
    std::fs::write(root.join("binary.bin"), [0x00, 0xff, 0x01, 0x00])?;
    let evidence = capture_git_diff(root, &repository.commit).await?;
    assert_eq!(
        (
            evidence.base_commit,
            evidence.final_commit,
            evidence.files_changed,
            evidence.untracked_files
        ),
        (
            repository.commit.clone(),
            repository.commit.clone(),
            2,
            vec!["binary.bin".to_string()]
        ),
    );
    assert_eq!(std::fs::read(root.join(".git/index"))?, initial_index);
    let text = std::str::from_utf8(&evidence.diff)?;
    assert!(text.contains("-before\n+after\n"));
    assert!(text.contains("GIT binary patch"));
    assert!(!text.contains("local.ignored"));
    // Git validates the complete produced patch against a fresh identical tree.
    let clean = Repository::new()?;
    let mut child = Command::new("git")
        .current_dir(clean.directory.path())
        .args(["apply", "--check", "--binary", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    child
        .stdin
        .take()
        .context("fixture stdin")?
        .write_all(&evidence.diff)?;
    let result = child.wait_with_output()?;
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    Ok(())
}

#[tokio::test]
async fn rejects_dirty_initial_tree_and_changed_commit() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    std::fs::write(root.join("tracked.txt"), b"changed\n")?;
    assert!(verify_git_baseline(root, &repository.commit).await.is_err());
    git(root, &["add", "--all"])?;
    git(root, &["commit", "-qm", "changed"])?;
    assert!(capture_git_diff(root, &repository.commit).await.is_err());
    Ok(())
}

#[tokio::test]
async fn rejects_untracked_initial_file_subdirectory_and_symbolic_base() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    std::fs::write(root.join("new.txt"), b"untracked")?;
    assert!(verify_git_baseline(root, &repository.commit).await.is_err());
    std::fs::create_dir(root.join("subdir"))?;
    assert!(
        capture_git_diff(&root.join("subdir"), &repository.commit)
            .await
            .is_err()
    );
    assert!(capture_git_diff(root, "HEAD").await.is_err());
    Ok(())
}

#[cfg(unix)]
#[tokio::test]
async fn never_runs_configured_filters_external_diff_textconv_or_fsmonitor() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    std::fs::write(root.join(".gitattributes"), b"*.txt filter=lab diff=lab\n")?;
    git(root, &["add", "--all"])?;
    git(root, &["commit", "-qm", "attributes"])?;
    let pinned = git(root, &["rev-parse", "HEAD"])?;
    for (key, value) in [
        ("filter.lab.clean", "touch clean-ran; cat"),
        ("filter.lab.process", "touch process-ran; exit 1"),
        ("filter.lab.required", "true"),
        ("diff.external", "touch external-ran"),
        ("diff.lab.textconv", "touch textconv-ran"),
        ("core.fsmonitor", "touch fsmonitor-ran"),
    ] {
        git(root, &["config", key, value])?;
    }
    verify_git_baseline(root, &pinned).await?;
    std::fs::write(root.join("tracked.txt"), b"after\n")?;
    let evidence = capture_git_diff(root, &pinned).await?;
    assert!(std::str::from_utf8(&evidence.diff)?.contains("-before\n+after\n"));
    for name in [
        "clean-ran",
        "process-ran",
        "external-ran",
        "textconv-ran",
        "fsmonitor-ran",
    ] {
        assert!(
            !root.join(name).exists(),
            "Git ran configured helper {name}"
        );
    }
    Ok(())
}

#[cfg(unix)]
#[tokio::test]
async fn rejects_untracked_symlinks() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    let outside = tempfile::tempdir()?;
    std::fs::write(outside.path().join("secret"), b"outside data")?;
    std::os::unix::fs::symlink(outside.path().join("secret"), root.join("link"))?;
    assert!(capture_git_diff(root, &repository.commit).await.is_err());
    Ok(())
}

#[tokio::test]
async fn rejects_capture_that_exceeds_aggregate_output_budget() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    std::fs::write(root.join("large.txt"), vec![b'x'; 8 * 1024 * 1024])?;
    assert!(capture_git_diff(root, &repository.commit).await.is_err());
    Ok(())
}

#[tokio::test]
async fn rejects_submodules_before_inspecting_their_worktree() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    git(
        root,
        &[
            "update-index",
            "--add",
            "--cacheinfo",
            &format!("160000,{},nested", repository.commit),
        ],
    )?;
    assert!(capture_git_diff(root, &repository.commit).await.is_err());
    Ok(())
}

#[tokio::test]
async fn local_diff_format_settings_cannot_change_recorded_patch() -> anyhow::Result<()> {
    let repository = Repository::new()?;
    let root = repository.directory.path();
    std::fs::write(root.join("tracked.txt"), b"after\n")?;
    std::fs::write(root.join("added.txt"), b"new\n")?;
    let expected = capture_git_diff(root, &repository.commit).await?;
    std::fs::write(root.join("order.ignored"), b"tracked.txt\nadded.txt\n")?;
    for (key, value) in [
        ("diff.noprefix", "true"),
        ("diff.mnemonicPrefix", "true"),
        ("diff.context", "50"),
        ("diff.interHunkContext", "100"),
        ("diff.algorithm", "histogram"),
        ("diff.indentHeuristic", "true"),
        ("diff.suppressBlankEmpty", "true"),
        ("diff.orderFile", "order.ignored"),
        ("color.ui", "always"),
    ] {
        git(root, &["config", key, value])?;
    }
    let actual = capture_git_diff(root, &repository.commit).await?;
    assert_eq!(actual.diff, expected.diff);
    let rendered = std::str::from_utf8(&actual.diff)?
        .lines()
        .map(|line| {
            if line.starts_with("index ") {
                "index <blob identifiers>"
            } else {
                line
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    insta::assert_snapshot!(rendered, @r###"
    diff --git a/tracked.txt b/tracked.txt
    index <blob identifiers>
    --- a/tracked.txt
    +++ b/tracked.txt
    @@ -1 +1 @@
    -before
    +after
    diff --git a/added.txt b/added.txt
    new file mode 100644
    index <blob identifiers>
    --- /dev/null
    +++ b/added.txt
    @@ -0,0 +1 @@
    +new
    "###);
    Ok(())
}
