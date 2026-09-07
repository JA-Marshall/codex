#![cfg(target_os = "linux")]

use super::*;
use anyhow::Context;
use pretty_assertions::assert_eq;

#[test]
fn candidate_audit_rejects_existing_links_and_observes_ignored_content_and_modes() -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let root = tempfile::tempdir()?;
    let file = root.path().join("ignored.cache");
    std::fs::write(&file, "baseline")?;
    let before = CandidateSnapshot::capture(root.path())?;
    std::fs::write(&file, "changed")?;
    assert_eq!(
        before.changed_paths(&CandidateSnapshot::capture(root.path())?),
        BTreeSet::from([PathBuf::from("ignored.cache")])
    );
    std::fs::write(&file, "baseline")?;
    std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o700))?;
    assert_eq!(
        before.changed_paths(&CandidateSnapshot::capture(root.path())?),
        BTreeSet::from([PathBuf::from("ignored.cache")])
    );
    let alias = root.path().join("alias");
    std::fs::hard_link(&file, &alias)?;
    assert!(
        CandidateSnapshot::capture(root.path())
            .err()
            .context("hardlink rejected")?
            .to_string()
            .contains("hardlink")
    );
    std::fs::remove_file(&alias)?;
    std::os::unix::fs::symlink(&file, &alias)?;
    assert!(
        CandidateSnapshot::capture(root.path())
            .err()
            .context("symlink rejected")?
            .to_string()
            .contains("symlink")
    );
    Ok(())
}
