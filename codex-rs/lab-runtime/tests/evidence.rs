use std::io;

use codex_lab_runtime::EvidenceStore;
use pretty_assertions::assert_eq;
use serde_json::json;

type TestResult = Result<(), Box<dyn std::error::Error>>;

#[test]
fn writes_exact_bytes_and_readable_json_into_fresh_evidence_directory() -> TestResult {
    let root = tempfile::tempdir()?;
    let store = EvidenceStore::new(root.path())?;
    let json_path = store.write_json("model.json", &json!({"model": "mock-v1", "tokens": null}))?;
    let bytes_path = store.write_bytes("turn-1.diff", b"diff\r\nexact\0bytes")?;
    assert_eq!(
        std::fs::read(json_path)?,
        b"{\n  \"model\": \"mock-v1\",\n  \"tokens\": null\n}\n"
    );
    assert_eq!(std::fs::read(bytes_path)?, b"diff\r\nexact\0bytes");
    Ok(())
}

#[test]
fn refuses_existing_or_missing_artifact_storage() -> TestResult {
    let root = tempfile::tempdir()?;
    let _store = EvidenceStore::new(root.path())?;
    assert_eq!(
        EvidenceStore::new(root.path())
            .err()
            .map(|error| error.kind()),
        Some(io::ErrorKind::AlreadyExists)
    );
    assert_eq!(
        EvidenceStore::new(root.path().join("missing"))
            .err()
            .map(|error| error.kind()),
        Some(io::ErrorKind::NotFound)
    );
    Ok(())
}

#[test]
fn collisions_preserve_existing_record_and_permanently_close_store() -> TestResult {
    let root = tempfile::tempdir()?;
    let store = EvidenceStore::new(root.path())?;
    let path = store.write_bytes("record.bin", b"original")?;
    assert_eq!(
        store
            .write_bytes("record.bin", b"replacement")
            .err()
            .map(|error| error.kind()),
        Some(io::ErrorKind::AlreadyExists)
    );
    assert_eq!(std::fs::read(path)?, b"original");
    assert_eq!(
        store
            .write_bytes("retry.bin", b"later")
            .err()
            .map(|error| error.to_string()),
        Some("evidence store is closed after a previous failure".to_string())
    );
    assert!(!root.path().join("evidence/retry.bin").exists());
    Ok(())
}

#[test]
fn rejects_paths_and_nonportable_names_without_writing() -> TestResult {
    for name in [
        "",
        ".",
        "..",
        "../escape",
        "/escape",
        "dir/name",
        "dir\\name",
        "x:stream",
        "has space",
        "x\0y",
        "x.",
        "CON",
        "Nul.json",
        "com1.txt",
    ] {
        let root = tempfile::tempdir()?;
        let store = EvidenceStore::new(root.path())?;
        assert_eq!(
            store
                .write_bytes(name, b"data")
                .err()
                .map(|error| error.kind()),
            Some(io::ErrorKind::InvalidInput)
        );
        assert_eq!(std::fs::read_dir(root.path().join("evidence"))?.count(), 0);
    }
    Ok(())
}

#[test]
fn caps_raw_and_serialized_records_before_creating_files() -> TestResult {
    let raw_root = tempfile::tempdir()?;
    let raw_store = EvidenceStore::new(raw_root.path())?;
    let exact = vec![b'x'; 8 * 1024 * 1024];
    let path = raw_store.write_bytes("exact.bin", &exact)?;
    assert_eq!(std::fs::metadata(path)?.len(), exact.len() as u64);
    assert!(
        raw_store
            .write_bytes("oversized.bin", &vec![b'x'; exact.len() + 1])
            .is_err()
    );
    assert!(!raw_root.path().join("evidence/oversized.bin").exists());
    let json_root = tempfile::tempdir()?;
    let json_store = EvidenceStore::new(json_root.path())?;
    // JSON quoting and the final newline also consume the record budget.
    assert!(
        json_store
            .write_json("oversized.json", &"x".repeat(exact.len()))
            .is_err()
    );
    assert_eq!(
        std::fs::read_dir(json_root.path().join("evidence"))?.count(),
        0
    );
    Ok(())
}

#[cfg(unix)]
#[test]
fn refuses_preexisting_symlink_without_touching_target() -> TestResult {
    let root = tempfile::tempdir()?;
    let store = EvidenceStore::new(root.path())?;
    let outside = tempfile::tempdir()?;
    let target = outside.path().join("original");
    std::fs::write(&target, b"original")?;
    std::os::unix::fs::symlink(&target, root.path().join("evidence/record"))?;
    assert_eq!(
        store
            .write_bytes("record", b"replacement")
            .err()
            .map(|error| error.kind()),
        Some(io::ErrorKind::AlreadyExists)
    );
    assert_eq!(std::fs::read(target)?, b"original");
    Ok(())
}
