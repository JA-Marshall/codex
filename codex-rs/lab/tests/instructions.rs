use std::fs;
use std::path::Path;

use codex_lab::WorkflowCatalog;
use pretty_assertions::assert_eq;
use sha2::Digest;
use sha2::Sha256;
use tempfile::tempdir;

const SKILL: &[u8] = b"---\r\nname: lab-test\r\ndescription: Test role instructions.\r\n---\r\nRead the approved plan.\r\n";

fn source(path: &str, bytes: &[u8]) -> String {
    let sha256 = format!("{:x}", Sha256::digest(bytes));
    format!(
        r#"schema_version = 1
[skills.required]
path = '{path}'
sha256 = "{sha256}"
[workflows.base]
approval = "human_required"
plan.renderer = "markdown"
roles.planner = "required"
roles.executor = "required"
roles.verifier = "required"
"#
    )
}

fn write_skill(base: &Path, bytes: &[u8]) -> std::io::Result<()> {
    fs::create_dir_all(base.join("skill"))?;
    fs::write(base.join("skill/SKILL.md"), bytes)
}

#[test]
fn freezes_exact_bytes_hash_and_selection_without_loading_ambient_skills() {
    let root = tempdir().unwrap();
    let skill = [
        SKILL,
        "Preserve the approved plan and report actual verification evidence.\r\n"
            .repeat(256)
            .as_bytes(),
    ]
    .concat();
    write_skill(root.path(), &skill).unwrap();
    let catalog = WorkflowCatalog::parse(&source("skill", &skill)).unwrap();
    let workflow = catalog.resolve("base").unwrap();
    let snapshots = catalog
        .resolve_instructions(root.path(), &workflow)
        .unwrap();
    snapshots.validate(&workflow.roles).unwrap();
    let expected = serde_json::json!({
        "selector": "required",
        "path": root.path().join("skill/SKILL.md").canonicalize().unwrap(),
        "sha256": format!("{:x}", Sha256::digest(&skill)),
        "content": std::str::from_utf8(&skill).unwrap(),
    });
    assert_eq!(
        serde_json::to_value(&snapshots).unwrap(),
        serde_json::json!({"planner": expected, "executor": expected, "verifier": expected})
    );
    fs::write(root.path().join("skill/SKILL.md"), "changed").unwrap();
    assert_eq!(snapshots.planner.content().as_bytes(), skill);
    assert!(
        catalog
            .resolve_instructions(root.path(), &workflow)
            .is_err()
    );
    let mut wrong_roles = workflow.roles;
    wrong_roles.planner = "other".into();
    assert!(snapshots.validate(&wrong_roles).is_err());
}

#[test]
fn rejects_missing_changed_empty_and_non_utf8_resources() {
    let root = tempdir().unwrap();
    let catalog = WorkflowCatalog::parse(&source("skill", SKILL)).unwrap();
    let workflow = catalog.resolve("base").unwrap();
    assert!(
        catalog
            .resolve_instructions(root.path(), &workflow)
            .is_err()
    );
    write_skill(root.path(), b"changed").unwrap();
    assert!(
        catalog
            .resolve_instructions(root.path(), &workflow)
            .is_err()
    );
    for bytes in [vec![], vec![0xff]] {
        write_skill(root.path(), &bytes).unwrap();
        let catalog = WorkflowCatalog::parse(&source("skill", &bytes)).unwrap();
        assert!(
            catalog
                .resolve_instructions(root.path(), &workflow)
                .is_err()
        );
    }
}

#[test]
fn rejects_nonlocal_paths_and_unpinned_hashes() {
    for path in [
        "",
        "/absolute",
        "../escape",
        "a/../b",
        "a//b",
        ".",
        "a/",
        "C:/skill",
        "\\\\server\\skill",
        "skill://remote",
        "https://remote/skill",
    ] {
        assert!(
            WorkflowCatalog::parse(&source(path, SKILL)).is_err(),
            "{path}"
        );
    }
    let source = source("skill", SKILL);
    let digest = format!("{:x}", Sha256::digest(SKILL));
    for hash in [
        "".to_string(),
        "f".repeat(63),
        "g".repeat(64),
        digest.to_uppercase(),
    ] {
        assert!(WorkflowCatalog::parse(&source.replace(&digest, &hash)).is_err());
    }
}

#[cfg(unix)]
#[test]
fn rejects_symlinks_outside_the_catalog_base() {
    let root = tempdir().unwrap();
    let outside = tempdir().unwrap();
    write_skill(outside.path(), SKILL).unwrap();
    std::os::unix::fs::symlink(outside.path().join("skill"), root.path().join("skill")).unwrap();
    let catalog = WorkflowCatalog::parse(&source("skill", SKILL)).unwrap();
    let workflow = catalog.resolve("base").unwrap();
    assert!(
        catalog
            .resolve_instructions(root.path(), &workflow)
            .is_err()
    );
}
